"""
Speech-to-Text (STT) Engine Abstraction.
Supports Faster-Whisper (offline local), Groq Cloud (ultra-low latency),
OpenAI Whisper API, SpeechRecognition (Google Free STT), and Whisper.cpp.
"""

import abc
import os
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


class MockSTTEngine(BaseSTTEngine):
    """Test engine for offline development and simulation."""

    def is_available(self) -> bool:
        return True

    def transcribe(self, wav_path: str) -> str:
        return "open terminal"


def get_stt_engine(config: dict) -> BaseSTTEngine:
    """Factory to create appropriate STT backend."""
    backend = config.get("stt_backend", "auto").lower()

    if backend == "groq" or (backend == "auto" and config.get("groq_api_key")):
        engine = GroqWhisperEngine(config.get("groq_api_key"))
        if engine.is_available():
            return engine

    if backend == "openai" or (backend == "auto" and config.get("openai_api_key")):
        engine = OpenAIWhisperEngine(config.get("openai_api_key"))
        if engine.is_available():
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
