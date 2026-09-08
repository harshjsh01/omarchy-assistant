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
    """Sarvam AI Saaras:v2 / Saaras:v3 multilingual STT for Indian English, Hindi & Hinglish."""

    def __init__(self, api_key: Optional[str] = None, model: str = "saaras:v3", language_code: str = "unknown"):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY", "")
        self.model = model
        self.language_code = language_code

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, wav_path: str) -> str:
        if not self.is_available():
            print("[omarchy-assistant] Sarvam AI error: SARVAM_API_KEY is not configured.", file=sys.stderr)
            return ""

        import urllib.request
        import urllib.error
        import json
        import sys

        boundary = "----SarvamMultipartBoundary"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(f"{self.model}\r\n".encode())

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="language_code"\r\n\r\n')
        body.extend(f"{self.language_code}\r\n".encode())

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
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            print(f"[omarchy-assistant] Sarvam AI STT HTTP {e.code}: {err}", file=sys.stderr)
            return ""
        except Exception as e:
            print(f"[omarchy-assistant] Sarvam AI STT error: {e}", file=sys.stderr)
            return ""


class GeminiMultimodalSTTEngine(BaseSTTEngine):
    """Google Gemini native multimodal audio STT for perfect Hindi, Hinglish & English."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, wav_path: str) -> str:
        if not self.is_available():
            print("[omarchy-assistant] Gemini Multimodal error: GEMINI_API_KEY is not set.", file=sys.stderr)
            return ""

        import base64
        import json
        import urllib.request
        import urllib.error
        import sys

        try:
            with open(wav_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": audio_b64
                            }
                        },
                        {
                            "text": "Transcribe the spoken audio verbatim in its original spoken language (Hindi, Hinglish, or English). Return ONLY the transcription text, nothing else."
                        }
                    ]
                }]
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
                return ""
        except Exception as e:
            print(f"[omarchy-assistant] Gemini Multimodal STT error: {e}", file=sys.stderr)
            return ""



class WhisperCppEngine(BaseSTTEngine):
    """Local offline multilingual Whisper engine via compiled whisper-cli with prompt biasing."""

    def __init__(self, binary_path: Optional[str] = None, model_path: Optional[str] = None, language: str = "auto", model_name: Optional[str] = None):
        home = Path.home()
        self.binary_path = binary_path or os.getenv("WHISPER_BIN") or str(home / ".local" / "bin" / "whisper-cli")

        models_dir = home / ".local" / "share" / "omarchy-assistant" / "models"
        selected = None
        if model_name:
            cand = models_dir / f"ggml-{model_name}.bin"
            if cand.exists():
                selected = cand

        if not selected:
            for m in ["ggml-base.bin", "ggml-small.bin", "ggml-tiny.bin", "ggml-tiny.en.bin"]:
                cand = models_dir / m
                if cand.exists():
                    selected = cand
                    break

        self.model_path = model_path or os.getenv("WHISPER_MODEL_PATH") or (str(selected) if selected else "")
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
                "-nf",
                "-mc", "0",
                "-nth", "0.65",
                "--no-prints",
                "-l", self.language,
                "-t", "4",
                "--prompt", "Max, मैक्स, play song on YouTube, YouTube, यूट्यूब, गाना चलाओ, गाना बजाओ, टर्मिनल खोलो, ब्राउज़र खोलो, वॉल्यूम बढ़ाओ, वॉल्यूम कम करो, Spotify, Seedhe Maut, song, songs, music, video, play, pause, resume, browser, Chromium, Antigravity, Omarchy, Hyprland, launch, terminal, workspace, Hinglish, Hindi, brainstorm, project, documentation, remember, remind, reminder, memory, yaad, monitor, activity"
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
                "[music]", "[applause]", "[silence]", ".", "..", "...", "you.", "a",
                "i'll see you next time", "i'll see you next time.", "see you next time",
                "see you next time.", "thank you for watching.", "thank you for watching",
                "please subscribe", "please subscribe."
            }
            norm = text.lower().strip(" ,.!?-")
            if not norm or norm in hallucinations or text.lower() in hallucinations:
                return ""

            # Reject repeated numbers/hyphens or repeated character strings (e.g. 4-5-6-6-6-6-6-6)
            if re.search(r"(\S[- ]?)\1{4,}", norm):
                return ""
            # Reject repeated words (e.g. "you you you you")
            if re.search(r"\b(\w+)\b(?:\s+\1\b){2,}", norm):
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

    # 1. Check Sarvam AI (Saaras:v2 / Saaras:v3)
    if backend == "sarvam" or (backend == "auto" and config.get("sarvam_api_key")):
        engine = SarvamSTTEngine(
            api_key=config.get("sarvam_api_key"),
            model=config.get("sarvam_model", "saaras:v3"),
            language_code=config.get("sarvam_language_code", "unknown")
        )
        if engine.is_available() or backend == "sarvam":
            return engine

    # 2. Check Gemini Multimodal Audio
    if backend in ["gemini", "gemini-audio", "gemini_multimodal"] or (backend == "auto" and config.get("gemini_api_key")):
        engine = GeminiMultimodalSTTEngine(
            api_key=config.get("gemini_api_key"),
            model=config.get("gemini_stt_model", "gemini-2.0-flash")
        )
        if engine.is_available() or backend in ["gemini", "gemini-audio", "gemini_multimodal"]:
            return engine

    # 3. Check Groq Cloud if requested or configured
    if backend == "groq" or (backend == "auto" and config.get("groq_api_key")):
        engine = GroqWhisperEngine(config.get("groq_api_key"))
        if engine.is_available():
            return engine

    # 4. Check OpenAI Whisper API
    if backend == "openai" or (backend == "auto" and config.get("openai_api_key")):
        engine = OpenAIWhisperEngine(config.get("openai_api_key"))
        if engine.is_available():
            return engine

    # 4. Local offline whisper.cpp (fast, free, multilingual base model with prompt biasing)
    if backend in ["whisper-cpp", "whisper.cpp", "whisper_cpp", "auto"]:
        engine = WhisperCppEngine(language=config.get("language", "auto"), model_name=config.get("whisper_model", "base"))
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
