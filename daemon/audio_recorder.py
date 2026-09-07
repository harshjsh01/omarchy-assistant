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

    def start_recording(self) -> str:
        """Start capturing audio in the background."""
        if self.is_recording:
            self.stop_recording()

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

    def record_with_vad(self, max_duration: float = 8.0, silence_timeout: float = 1.2, energy_threshold: float = 400.0) -> Optional[str]:
        """
        Record audio with automatic silence detection (VAD).
        Stops automatically when user stops speaking.
        """
        self.start_recording()
        start = time.time()
        has_spoken = False
        silence_start: Optional[float] = None

        # Give it a short moment to capture header
        time.sleep(0.3)

        while (time.time() - start) < max_duration:
            time.sleep(0.15)
            if not self.current_wav_path or not os.path.exists(self.current_wav_path):
                continue

            # Read latest chunk from file to compute RMS energy
            try:
                with wave.open(self.current_wav_path, "rb") as wf:
                    n_frames = wf.getnframes()
                    if n_frames < int(self.sample_rate * 0.2):
                        continue
                    # Read last 0.2 seconds
                    frames_to_read = min(n_frames, int(self.sample_rate * 0.2))
                    wf.setpos(n_frames - frames_to_read)
                    raw_data = wf.readframes(frames_to_read)
                    
                    if not raw_data:
                        continue

                    # Compute RMS
                    count = len(raw_data) // 2
                    if count == 0:
                        continue
                    shorts = struct.unpack(f"<{count}h", raw_data)
                    sum_sq = sum(s * s for s in shorts)
                    rms = math.sqrt(sum_sq / count)

                    if rms > energy_threshold:
                        has_spoken = True
                        silence_start = None
                    else:
                        if has_spoken:
                            if silence_start is None:
                                silence_start = time.time()
                            elif (time.time() - silence_start) >= silence_timeout:
                                # User finished speaking
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
