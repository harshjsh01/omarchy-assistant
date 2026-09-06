"""
Text-to-Speech (TTS) Engine for voice feedback.
Supports Piper TTS, espeak-ng, spd-say (speech-dispatcher), or silent mode.
"""

import shutil
import subprocess
from typing import Dict, Any


class TTSEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("tts_enabled", False)
        self.backend = config.get("tts_backend", "auto")

    def speak(self, text: str) -> None:
        """Speak out text asynchronously."""
        if not self.enabled or not text.strip():
            return

        # Try piper if available
        if self.backend in ["piper", "auto"] and shutil.which("piper"):
            try:
                subprocess.Popen(
                    f"echo '{text}' | piper --output-raw | aplay -r 22050 -f S16_LE -t raw -",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass

        # Try espeak-ng
        if self.backend in ["espeak-ng", "auto"] and shutil.which("espeak-ng"):
            try:
                subprocess.Popen(
                    ["espeak-ng", "-s", "175", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass

        # Try spd-say
        if shutil.which("spd-say"):
            try:
                subprocess.Popen(
                    ["spd-say", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass
