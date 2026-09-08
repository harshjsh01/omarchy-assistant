"""
Audio recording module with Voice Activity / Silence Detection.
Uses native Linux audio tools (arecord / ffmpeg / PipeWire) without requiring heavy dependencies.
"""

import collections
import fcntl
import math
import os
import signal
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, Optional


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, max_duration: float = 12.0):
        self.sample_rate = sample_rate
        self.max_duration = max_duration
        self.process: Optional[subprocess.Popen] = None
        self.current_wav_path: Optional[str] = None
        self.is_recording = False
        self.last_recording_had_speech = False
        self.start_time = 0.0

        # Continuous streaming state
        self.stream_process: Optional[subprocess.Popen] = None
        self.stream_noise_floor: float = 480.0
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

    # -------------------------------------------------------------------------
    # Continuous Stream API (Persistent arecord for zero-latency, no-pop listening)
    # -------------------------------------------------------------------------

    def start_continuous_stream(self) -> None:
        """Start persistent raw PCM stream from microphone."""
        if self.stream_process and self.stream_process.poll() is None:
            return

        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", "1",
            "-t", "raw",
            "-"
        ]
        try:
            self.stream_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )
            # Flush first 0.3s (6 chunks of 50ms) to discard hardware/PulseAudio connection pop
            for _ in range(6):
                self.stream_process.stdout.read(1600)
            self.stream_noise_floor = 480.0
        except Exception as e:
            print(f"[omarchy-assistant] Failed to start continuous audio stream: {e}")
            self.stream_process = None

    def stop_continuous_stream(self) -> None:
        """Terminate persistent raw PCM stream."""
        if self.stream_process:
            try:
                self.stream_process.terminate()
                self.stream_process.wait(timeout=0.5)
            except Exception:
                try:
                    self.stream_process.kill()
                except Exception:
                    pass
            self.stream_process = None

    def drain_stream(self) -> None:
        """
        Discard buffered audio accumulated in the pipe (e.g. while Max spoke TTS).
        Ensures the assistant never hears or transcribes its own spoken voice.
        """
        if not self.stream_process or not self.stream_process.stdout:
            return
        fd = self.stream_process.stdout.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            while True:
                data = os.read(fd, 8192)
                if not data:
                    break
        except (BlockingIOError, OSError):
            pass
        finally:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

    def listen_turn(
        self,
        silence_timeout: float = 1.1,
        energy_threshold: float = 850.0,
        on_speech_start: Optional[Callable] = None,
        is_active: Optional[Callable[[], bool]] = None,
        max_duration: float = 12.0
    ) -> Optional[str]:
        """
        Listen for a single spoken utterance from the persistent stream.
        Uses 0.4s pre-roll buffer so words like 'Hey' or 'Max' are never clipped.
        Returns path to recorded WAV file or None if no speech / cancelled.
        """
        if not self.stream_process or self.stream_process.poll() is not None:
            self.start_continuous_stream()
            if not self.stream_process or not self.stream_process.stdout:
                return None

        chunk_bytes = int(self.sample_rate * 2 * 0.05)  # 50ms = 1600 bytes
        pre_roll = collections.deque(maxlen=8)  # 400ms pre-roll
        speech_chunks = []
        has_spoken = False
        consecutive_speech = 0
        active_speech_chunks = 0
        silence_chunks = 0
        silence_limit = max(15, int(silence_timeout / 0.05))
        max_chunks = int(max_duration / 0.05)

        while True:
            if is_active and not is_active():
                return None

            try:
                data = self.stream_process.stdout.read(chunk_bytes)
            except Exception:
                break

            if not data or len(data) < chunk_bytes:
                time.sleep(0.01)
                continue

            shorts = struct.unpack(f"<{len(data)//2}h", data)
            rms = math.sqrt(sum(s * s for s in shorts) / len(shorts))

            if not has_spoken:
                pre_roll.append(data)
                # Adapt noise floor slowly to room ambient acoustics
                self.stream_noise_floor = 0.98 * self.stream_noise_floor + 0.02 * rms
                effective_thresh = max(self.stream_noise_floor * 2.2, 1050.0, energy_threshold)

                if rms > effective_thresh:
                    consecutive_speech += 1
                    # Require 200ms (4 consecutive chunks) of sustained vocal energy
                    # This completely ignores single clicks, keystrokes, drum beats, and breath pops
                    if consecutive_speech >= 4:
                        has_spoken = True
                        speech_chunks = list(pre_roll)
                        active_speech_chunks = consecutive_speech
                        if on_speech_start:
                            try:
                                on_speech_start()
                            except Exception:
                                pass
                else:
                    consecutive_speech = 0
            else:
                speech_chunks.append(data)
                effective_thresh = max(self.stream_noise_floor * 1.8, 900.0, energy_threshold * 0.85)

                if rms > effective_thresh:
                    active_speech_chunks += 1
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_limit:
                        # User spoke and has now paused for silence_timeout -> done!
                        break

                if len(speech_chunks) >= max_chunks:
                    break

        # A real spoken command must contain at least 6 active speech chunks (>= 300ms of active vocal energy)
        # and at least 12 total chunks (>= 600ms total duration).
        # Anything less is background noise, breath, or a transient click, and is safely discarded without entering processing.
        if has_spoken and active_speech_chunks >= 6 and len(speech_chunks) >= 12:
            return self._write_wav(speech_chunks)

        return None

    # -------------------------------------------------------------------------
    # Push-to-Talk VAD API (Self-contained recording for SUPER + A)
    # -------------------------------------------------------------------------

    def record_with_vad(
        self,
        max_duration: float = 12.0,
        silence_timeout: float = 1.2,
        energy_threshold: float = 850.0,
        on_speech_start: Optional[Callable] = None,
        max_wait_speech: float = 5.5
    ) -> Optional[str]:
        """
        Record audio for push-to-talk mode with automatic speech detection.
        Waits up to max_wait_speech for the user to start speaking.
        Stops automatically after silence_timeout of pause.
        """
        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", "1",
            "-t", "raw",
            "-"
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )
        except FileNotFoundError:
            # Fallback to ffmpeg
            proc = subprocess.Popen(
                ["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-ar", str(self.sample_rate), "-ac", "1", "-f", "s16le", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )

        # Flush initial 0.25s connection pop
        for _ in range(5):
            proc.stdout.read(1600)

        chunk_bytes = int(self.sample_rate * 2 * 0.05)  # 50ms = 1600 bytes
        pre_roll = collections.deque(maxlen=8)
        speech_chunks = []
        has_spoken = False
        consecutive_speech = 0
        active_speech_chunks = 0
        silence_chunks = 0
        silence_limit = max(15, int(silence_timeout / 0.05))
        max_chunks = int(max_duration / 0.05)
        start_time = time.time()
        noise_floor = 480.0

        try:
            while True:
                data = proc.stdout.read(chunk_bytes)
                if not data or len(data) < chunk_bytes:
                    time.sleep(0.01)
                    continue

                shorts = struct.unpack(f"<{len(data)//2}h", data)
                rms = math.sqrt(sum(s * s for s in shorts) / len(shorts))

                if not has_spoken:
                    pre_roll.append(data)
                    noise_floor = 0.98 * noise_floor + 0.02 * rms
                    effective_thresh = max(noise_floor * 2.2, 1000.0, energy_threshold)

                    if rms > effective_thresh:
                        consecutive_speech += 1
                        if consecutive_speech >= 3:
                            has_spoken = True
                            speech_chunks = list(pre_roll)
                            active_speech_chunks = consecutive_speech
                            if on_speech_start:
                                try:
                                    on_speech_start()
                                except Exception:
                                    pass
                    else:
                        consecutive_speech = 0
                        if (time.time() - start_time) > max_wait_speech:
                            # User did not speak within timeout window
                            break
                else:
                    speech_chunks.append(data)
                    effective_thresh = max(noise_floor * 1.8, 850.0, energy_threshold * 0.85)

                    if rms > effective_thresh:
                        active_speech_chunks += 1
                        silence_chunks = 0
                    else:
                        silence_chunks += 1
                        if silence_chunks >= silence_limit:
                            break

                    if len(speech_chunks) >= max_chunks:
                        break
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self.last_recording_had_speech = has_spoken
        if has_spoken and active_speech_chunks >= 5 and len(speech_chunks) >= 10:
            return self._write_wav(speech_chunks)

        return None

    def _write_wav(self, chunks: list) -> str:
        """Write raw PCM chunks to a standard temporary WAV file."""
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="omarchy_voice_")
        os.close(fd)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(chunks))
        return wav_path

    # -------------------------------------------------------------------------
    # Backward-compatible API
    # -------------------------------------------------------------------------

    def start_recording(self) -> str:
        """Start capturing audio file."""
        fd, self.current_wav_path = tempfile.mkstemp(suffix=".wav", prefix="omarchy_voice_")
        os.close(fd)
        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", "1",
            "-t", "wav",
            self.current_wav_path
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.is_recording = True
        return self.current_wav_path

    def stop_recording(self) -> Optional[str]:
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=0.5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.is_recording = False
        return self.current_wav_path

    def play_feedback_tone(self, tone_type: str = "output") -> None:
        """Play short feedback chime only when outputting response."""
        try:
            sound_file = "/usr/share/sounds/freedesktop/stereo/complete.oga"
            if not os.path.exists(sound_file):
                sound_file = "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"

            subprocess.Popen(
                ["paplay", sound_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
