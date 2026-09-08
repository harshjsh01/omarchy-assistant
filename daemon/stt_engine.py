"""
Speech-to-Text (STT) Engine Abstraction.
Supports Faster-Whisper (offline local), Groq Cloud (ultra-low latency),
OpenAI Whisper API, SpeechRecognition (Google Free STT), and Whisper.cpp.
"""

import abc
import os
import re
import subprocess
from pathlib import Path
from typing import Optional


class BaseSTTEngine(abc.ABC):
    @abc.abstractmethod
    def transcribe(self, wav_path: str) -> str:
        """Transcribe an audio file to text."""
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if backend dependencies/credentials are present."""
        pass


class FasterWhisperEngine(BaseSTTEngine):
    """Local offline Whisper transcription using faster-whisper (CTranslate2)."""

    def __init__(self, model_size: str = "base.en", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None

    def is_available(self) -> bool:
        try:
            import faster_whisper
            return True
        except ImportError:
            return False

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )

    def transcribe(self, wav_path: str) -> str:
        self._load_model()
        segments, _ = self.model.transcribe(wav_path, beam_size=1)
        text = " ".join([segment.text for segment in segments]).strip()
        return text


class GroqWhisperEngine(BaseSTTEngine):
    """Ultra-fast cloud transcription via Groq Cloud API (~150ms)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, wav_path: str) -> str:
        import urllib.request
        import json

        # Send multipart form request to Groq API
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        body = bytearray()
        # Model parameter
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(b"whisper-large-v3-turbo\r\n")

        # Language parameter
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        body.extend(b"en\r\n")

        # Audio file parameter
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(audio_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("text", "").strip()


class OpenAIWhisperEngine(BaseSTTEngine):
    """Cloud transcription via OpenAI Whisper API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, wav_path: str) -> str:
        import urllib.request
        import json

        boundary = "----OmarchyWhisperBoundary"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(b"whisper-1\r\n")

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(audio_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("text", "").strip()


class SpeechRecognitionEngine(BaseSTTEngine):
    """Free Google Web Speech API fallback via SpeechRecognition."""

    def is_available(self) -> bool:
        try:
            import speech_recognition
            return True
        except ImportError:
            return False

    def transcribe(self, wav_path: str) -> str:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
            return r.recognize_google(audio).strip()


class SarvamSTTEngine(BaseSTTEngine):
    """Sarvam AI Saaras:v2 multilingual STT for Indian English, Hindi & Hinglish."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, wav_path: str) -> str:
        import urllib.request
        import json
        import sys

        boundary = "----SarvamMultipartBoundary"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(b"saaras:v2\r\n")

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="language_code"\r\n\r\n')
        body.extend(b"unknown\r\n")

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(audio_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            "https://api.sarvam.ai/speech-to-text",
            data=bytes(body),
            headers={
                "api-subscription-key": self.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                return data.get("transcript", "").strip()
        except Exception as e:
            print(f"[omarchy-assistant] Sarvam AI STT error: {e}", file=sys.stderr)
            return ""


class WhisperCppEngine(BaseSTTEngine):
    """Local offline multilingual Whisper engine via compiled whisper-cli with prompt biasing."""

    def __init__(self, binary_path: Optional[str] = None, model_path: Optional[str] = None, language: str = "auto"):
        home = Path.home()
        self.binary_path = binary_path or os.getenv("WHISPER_BIN") or str(home / ".local" / "bin" / "whisper-cli")

        # Prefer high-accuracy base model for English + Hindi / Hinglish support
        default_model = home / ".local" / "share" / "omarchy-assistant" / "models" / "ggml-base.bin"
        if not default_model.exists():
            default_model = home / ".local" / "share" / "omarchy-assistant" / "models" / "ggml-tiny.bin"
        if not default_model.exists():
            default_model = home / ".local" / "share" / "omarchy-assistant" / "models" / "ggml-tiny.en.bin"

        self.model_path = model_path or os.getenv("WHISPER_MODEL_PATH") or str(default_model)
        self.language = language

    def is_available(self) -> bool:
        return (
            os.path.isfile(self.binary_path)
            and os.access(self.binary_path, os.X_OK)
            and os.path.isfile(self.model_path)
        )

    def transcribe(self, wav_path: str) -> str:
        if not self.is_available():
            return ""
        try:
            cmd = [
                self.binary_path,
                "-m", self.model_path,
                "-f", wav_path,
                "-nt",
                "-sns",
                "-mc", "0",
                "-nth", "0.65",
                "--no-prints",
                "-l", self.language,
                "-t", "4",
                "--prompt", "Max, Antigravity, Omarchy, Hyprland, agy, launch, terminal, workspace, Hinglish, Hindi, brainstorm, project, documentation, Seedhe Maut, YouTube, gaana, bajao, chalao, song, music, play"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            lines = []
            for line in res.stdout.splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("[BLANK_AUDIO]") and not cleaned.startswith("["):
                    lines.append(cleaned)
                elif cleaned and "[" in cleaned and "]" in cleaned:
                    no_brackets = re.sub(r"\[.*?\]", "", cleaned).strip()
                    if no_brackets:
                        lines.append(no_brackets)
            text = " ".join(lines).strip()

            # Reject known silence artifacts and hallucinations
            hallucinations = {
                "halt", "halt.", "halt,", "thank you", "thank you.", "thanks for watching",
                "subtitles by", "bye", "you", "amara.org", "subtitle", "transcription",
                "[music]", "[applause]", "[silence]", ".", "..", "...", "you.", "a"
            }
            norm = text.lower().strip(" ,.!?-")
            if not norm or norm in hallucinations or text.lower() in hallucinations:
                return ""

            return text
        except Exception as e:
            return ""


class MockSTTEngine(BaseSTTEngine):
    """Test engine for offline development and simulation."""

    def is_available(self) -> bool:
        return True

    def transcribe(self, wav_path: str) -> str:
        return "open terminal"


def get_stt_engine(config: dict) -> BaseSTTEngine:
    """Factory to create appropriate STT backend."""
    backend = config.get("stt_backend", "auto").lower()

    # 1. Check Sarvam AI if requested or configured with API key
    if backend == "sarvam" or (backend == "auto" and config.get("sarvam_api_key")):
        engine = SarvamSTTEngine(config.get("sarvam_api_key"))
        if engine.is_available():
            return engine

    # 2. Check Groq Cloud if requested or configured
    if backend == "groq" or (backend == "auto" and config.get("groq_api_key")):
        engine = GroqWhisperEngine(config.get("groq_api_key"))
        if engine.is_available():
            return engine

    # 3. Check OpenAI Whisper API
    if backend == "openai" or (backend == "auto" and config.get("openai_api_key")):
        engine = OpenAIWhisperEngine(config.get("openai_api_key"))
        if engine.is_available():
            return engine

    # 4. Local offline whisper.cpp (fast, free, multilingual base model with prompt biasing)
    if backend in ["whisper-cpp", "whisper.cpp", "whisper_cpp", "auto"]:
        engine = WhisperCppEngine(language=config.get("language", "auto"))
        if engine.is_available() or backend in ["whisper-cpp", "whisper.cpp", "whisper_cpp"]:
            return engine

    if backend in ["faster-whisper", "auto"]:
        engine = FasterWhisperEngine(
            model_size=config.get("whisper_model", "base.en"),
            device=config.get("whisper_device", "cpu"),
            compute_type=config.get("whisper_compute_type", "int8")
        )
        if engine.is_available() or backend == "faster-whisper":
            return engine

    if backend in ["speech_recognition", "auto"]:
        engine = SpeechRecognitionEngine()
        if engine.is_available():
            return engine

    return MockSTTEngine()
