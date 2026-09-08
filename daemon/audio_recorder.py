"""
Audio recording module with Voice Activity / Silence Detection.
Uses native Linux audio tools (arecord / ffmpeg / PipeWire) without requiring heavy dependencies.
"""

import math
import os
import signal
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, max_duration: float = 12.0):
        self.sample_rate = sample_rate
        self.max_duration = max_duration
        self.process: Optional[subprocess.Popen] = None
        self.current_wav_path: Optional[str] = None
        self.is_recording = False
        self.last_recording_had_speech = False
        self.start_time = 0.0
        self._cleanup_old_temp_recordings()

    def _cleanup_old_temp_recordings(self) -> None:
        try:
            for p in Path("/tmp").glob("omarchy_voice_*.wav"):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception:
            pass

    def start_recording(self) -> str:
        """Start capturing audio in the background."""
        if self.is_recording:
            self.stop_recording()

        if self.current_wav_path and os.path.exists(self.current_wav_path):
            try:
                os.unlink(self.current_wav_path)
            except OSError:
                pass

        # Create temporary WAV file
        fd, self.current_wav_path = tempfile.mkstemp(suffix=".wav", prefix="omarchy_voice_")
        os.close(fd)

        # We record 16kHz 16-bit mono PCM
        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", "1",
            "-t", "wav",
            self.current_wav_path
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            self.is_recording = True
            self.start_time = time.time()
            return self.current_wav_path
        except FileNotFoundError:
            # Fallback to ffmpeg if arecord is missing
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-f", "pulse",
                "-i", "default",
                "-ar", str(self.sample_rate),
                "-ac", "1",
                self.current_wav_path
            ]
            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            self.is_recording = True
            self.start_time = time.time()
            return self.current_wav_path

    def stop_recording(self) -> Optional[str]:
        """Stop capturing and return the recorded WAV file path."""
        if not self.is_recording or not self.process:
            return self.current_wav_path

        try:
            # Send SIGINT to gracefully close WAV header
            os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
            self.process.wait(timeout=1.5)
        except Exception:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except Exception:
                pass

        self.is_recording = False
        self.process = None

        if self.current_wav_path and os.path.exists(self.current_wav_path):
            file_size = os.path.getsize(self.current_wav_path)
            # Minimum WAV header is 44 bytes; require at least 1000 bytes for audio
            if file_size > 1000:
                return self.current_wav_path

        return None

    def record_with_vad(self, max_duration: float = 10.0, silence_timeout: float = 1.2, energy_threshold: float = 300.0) -> Optional[str]:
        """
        Record audio with automatic silence detection (VAD).
        Stops automatically when user stops speaking after saying a command.
        """
        self.start_recording()
        start = time.time()
        has_spoken = False
        silence_start: Optional[float] = None

        # Brief initial pause to let audio driver spin up
        time.sleep(0.2)

        while (time.time() - start) < max_duration:
            time.sleep(0.1)
            if not self.current_wav_path or not os.path.exists(self.current_wav_path):
                continue

            try:
                file_size = os.path.getsize(self.current_wav_path)
                if file_size > 44:
                    with open(self.current_wav_path, "rb") as f:
                        # Inspect the latest 0.2 seconds of 16kHz 16-bit mono audio (6400 bytes)
                        bytes_to_read = min(file_size - 44, int(self.sample_rate * 2 * 0.2))
                        if bytes_to_read >= 400:
                            f.seek(file_size - bytes_to_read)
                            raw_data = f.read(bytes_to_read)
                            count = len(raw_data) // 2
                            if count > 0:
                                shorts = struct.unpack(f"<{count}h", raw_data[:count * 2])
                                rms = math.sqrt(sum(s * s for s in shorts) / count)

                                if rms > energy_threshold:
                                    has_spoken = True
                                    silence_start = None
                                else:
                                    if has_spoken:
                                        if silence_start is None:
                                            silence_start = time.time()
                                        elif (time.time() - silence_start) >= silence_timeout:
                                            # User spoke and has now paused for silence_timeout -> stop & execute!
                                            break
            except Exception:
                pass

        self.last_recording_had_speech = has_spoken
        return self.stop_recording()

    def play_feedback_tone(self, tone_type: str = "start") -> None:
        """Play short feedback chime using system sounds or synthetic beep."""
        try:
            freq = 880 if tone_type == "start" else 440
            dur = 0.08
            cmd = f"play -n -c1 synth {dur} sine {freq} vol 0.2"
            # If sox is not present, use paplay or canberra-gtk-play
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
