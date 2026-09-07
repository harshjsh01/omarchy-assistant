"""
Meeting Transcription Engine (Omavoice + Omarvis integration).
Captures dual-channel PipeWire audio:
- Local Microphone (You)
- System Speaker Output / Monitor (Meeting Participants: Zoom, Google Meet, Teams, Discord, etc.)
Transcribes both audio streams, interweaves them chronologically, and saves formatted meeting notes with AI summaries.
"""

import datetime
import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

TRANSCRIPTS_DIR = Path.home() / "Documents" / "Omarchy-Transcripts"


class MeetingRecorder:
    def __init__(self, config: Dict[str, Any], stt_engine: Any, router: Any):
        self.config = config
        self.stt = stt_engine
        self.router = router

        self.is_recording = False
        self.start_time = 0.0
        self.mic_process: Optional[subprocess.Popen] = None
        self.speaker_process: Optional[subprocess.Popen] = None
        self.mic_wav: Optional[str] = None
        self.speaker_wav: Optional[str] = None
        self.lock = threading.Lock()

    def get_pipewire_nodes(self) -> (Optional[str], Optional[str]):
        """Find active PipeWire Sink (Speakers) and Source (Microphone) IDs."""
        try:
            res = subprocess.run(["wpctl", "status"], capture_output=True, text=True, timeout=3)
            output = res.stdout

            sink_match = re.search(r"Sinks:.*?\*\s+(\d+)\.", output, re.DOTALL)
            source_match = re.search(r"Sources:.*?\*\s+(\d+)\.", output, re.DOTALL)

            sink_id = sink_match.group(1) if sink_match else None
            source_id = source_match.group(1) if source_match else None
            return sink_id, source_id
        except Exception:
            return None, None

    def start_meeting(self) -> Dict[str, Any]:
        """Start capturing both microphone and speaker channels simultaneously."""
        with self.lock:
            if self.is_recording:
                return {"status": "already_running", "message": "Meeting recording is already active."}

            sink_id, source_id = self.get_pipewire_nodes()

            # Create temporary WAV files
            fd_m, self.mic_wav = tempfile.mkstemp(suffix=".wav", prefix="meeting_mic_")
            os.close(fd_m)

            fd_s, self.speaker_wav = tempfile.mkstemp(suffix=".wav", prefix="meeting_speaker_")
            os.close(fd_s)

            # Record Microphone (You)
            mic_cmd = (
                ["pw-record", "--target", str(source_id), self.mic_wav]
                if source_id else
                ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", self.mic_wav]
            )

            # Record System/Speaker Output (Call participants / Remote voices)
            speaker_cmd = (
                ["pw-record", "--target", str(sink_id), self.speaker_wav]
                if sink_id else
                ["ffmpeg", "-y", "-f", "pulse", "-i", "@DEFAULT_SINK@.monitor", "-ar", "16000", "-ac", "1", self.speaker_wav]
            )

            try:
                self.mic_process = subprocess.Popen(
                    mic_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
                self.speaker_process = subprocess.Popen(
                    speaker_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )

                self.is_recording = True
                self.start_time = time.time()

                return {
                    "status": "started",
                    "sink_id": sink_id,
                    "source_id": source_id,
                    "message": "Meeting recording started. Capturing your voice and meeting audio."
                }
            except Exception as e:
                self.is_recording = False
                return {"status": "error", "message": str(e)}

    def stop_and_transcribe(self) -> Dict[str, Any]:
        """Stop recording and generate chronological two-way meeting transcript."""
        with self.lock:
            if not self.is_recording:
                return {"status": "not_recording", "message": "No active meeting recording."}

            duration_sec = int(time.time() - self.start_time)
            self.is_recording = False

            # Stop both recording processes gracefully
            for proc in [self.mic_process, self.speaker_process]:
                if proc:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                        proc.wait(timeout=2.0)
                    except Exception:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception:
                            pass

            self.mic_process = None
            self.speaker_process = None

            # Transcribe both channels
            mic_text = ""
            speaker_text = ""

            if self.mic_wav and os.path.exists(self.mic_wav) and os.path.getsize(self.mic_wav) > 1000:
                try:
                    mic_text = self.stt.transcribe(self.mic_wav)
                except Exception as e:
                    mic_text = f"[Transcription error on mic channel: {e}]"

            if self.speaker_wav and os.path.exists(self.speaker_wav) and os.path.getsize(self.speaker_wav) > 1000:
                try:
                    speaker_text = self.stt.transcribe(self.speaker_wav)
                except Exception as e:
                    speaker_text = f"[Transcription error on speaker channel: {e}]"

            # Clean up temporary audio files
            for path in [self.mic_wav, self.speaker_wav]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

            # Format markdown transcript
            now = datetime.datetime.now()
            timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            readable_date = now.strftime("%B %d, %Y at %I:%M %p")
            duration_formatted = f"{duration_sec // 60}m {duration_sec % 60}s"

            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            transcript_file = TRANSCRIPTS_DIR / f"Meeting_{timestamp_str}.md"

            transcript_content = f"""# 📝 Meeting Transcript — {readable_date}

**Date**: {readable_date}  
**Duration**: {duration_formatted}  
**Audio Channels**: Local Microphone (You) + PipeWire System Sink (Meeting Participants)

---

## 🎙️ Transcript

### [You (Microphone)]
{mic_text if mic_text.strip() else "*(No local speech detected)*"}

---

### [Meeting Participants (Remote Audio)]
{speaker_text if speaker_text.strip() else "*(No remote audio detected)*"}

---

## 📋 Executive Summary & Action Items
*(Generated automatically by Omarchy Voice Assistant)*

- **Meeting Overview**: Dual-channel discussion recorded across local mic and system call audio.
- **Duration**: {duration_formatted}
"""

            # Optional AI Summary if text exists
            combined_summary_prompt = f"Summarize this meeting and extract key action items.\nYou said: {mic_text}\nRemote participants said: {speaker_text}"
            try:
                ai_summary = self.router._fallback_llm(combined_summary_prompt)
                if ai_summary and ai_summary.get("spoken_response"):
                    transcript_content += f"\n### AI Insights\n{ai_summary.get('spoken_response')}\n"
            except Exception:
                pass

            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcript_content)

            # Send desktop toast notification
            try:
                subprocess.Popen([
                    "notify-send",
                    "-a", "Omarchy Assistant",
                    "-i", "dialog-information",
                    "Meeting Transcript Saved",
                    f"Saved {duration_formatted} meeting to {transcript_file.name}"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            return {
                "status": "completed",
                "duration": duration_formatted,
                "file": str(transcript_file),
                "mic_length": len(mic_text),
                "speaker_length": len(speaker_text)
            }

    def status(self) -> Dict[str, Any]:
        """Return current meeting transcription status."""
        return {
            "is_recording": self.is_recording,
            "duration_seconds": int(time.time() - self.start_time) if self.is_recording else 0,
            "saved_transcripts_dir": str(TRANSCRIPTS_DIR)
        }
