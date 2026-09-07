"""
Text-to-Speech (TTS) Engine for voice feedback.
Supports Google TTS via PipeWire (natural English/Hindi), Piper TTS, espeak-ng, and spd-say.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request
from typing import Dict, Any


class TTSEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("tts_enabled", True)
        self.backend = config.get("tts_backend", "auto")

    def speak(self, text: str, wait: bool = False) -> None:
        """Speak out text asynchronously (default) or synchronously."""
        if not self.enabled or not text.strip():
            return
        if wait:
            self._speak_worker(text.strip())
        else:
            threading.Thread(target=self._speak_worker, args=(text.strip(),), daemon=True).start()

    def _speak_worker(self, text: str) -> None:
        """Fetch and play audio over speakers."""
        # Clean text for speech synthesis
        clean = text.replace("`", "").replace("*", "").replace("#", "").strip()
        if not clean:
            return

        # 1. Primary: Google TTS via PipeWire / ALSA
        if self.backend in ["google", "auto"]:
            try:
                # Detect Hindi characters or phrases
                lang = "hi" if any("\u0900" <= c <= "\u097F" for c in clean) else "en"
                url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={urllib.parse.quote(clean[:200])}&tl={lang}&client=tw-ob"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

                with urllib.request.urlopen(req, timeout=4) as resp:
                    mp3_data = resp.read()

                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_mp3:
                    f_mp3.write(mp3_data)
                    mp3_path = f_mp3.name

                wav_path = mp3_path.replace(".mp3", ".wav")
                try:
                    # Convert to wav and play on PipeWire default sink
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "24000", "-ac", "1", wav_path],
                        capture_output=True,
                        timeout=3,
                        check=True
                    )
                    player = "pw-play" if shutil.which("pw-play") else "aplay"
                    subprocess.run([player, wav_path], timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                finally:
                    for p in [mp3_path, wav_path]:
                        if os.path.exists(p):
                            try:
                                os.unlink(p)
                            except OSError:
                                pass
            except Exception:
                pass

        # 2. Offline fallback: Piper TTS
        if self.backend in ["piper", "auto"] and shutil.which("piper"):
            try:
                subprocess.run(
                    f"echo '{clean}' | piper --output-raw | aplay -r 22050 -f S16_LE -t raw -",
                    shell=True,
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass

        # 3. Offline fallback: espeak-ng
        if shutil.which("espeak-ng"):
            try:
                subprocess.run(["espeak-ng", "-s", "175", clean], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

        # 4. Offline fallback: spd-say
        if shutil.which("spd-say"):
            try:
                subprocess.run(["spd-say", clean], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
