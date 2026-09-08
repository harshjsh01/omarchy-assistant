import base64
import json
import os
import shutil
import subprocess
import sys
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

    def _speak_sarvam(self, clean: str) -> bool:
        """Synthesize natural Indian voice via Sarvam AI bulbul:v3 API."""
        api_key = self.config.get("sarvam_api_key") or os.getenv("SARVAM_API_KEY", "")
        if not api_key:
            return False

        try:
            # Determine language code: hi-IN if Hindi characters present, else en-IN
            lang = "hi-IN" if any("\u0900" <= c <= "\u097F" for c in clean) else "en-IN"
            speaker = self.config.get("tts_speaker", "aditya")
            model = self.config.get("tts_model", "bulbul:v3")
            pace = float(self.config.get("tts_pace", 1.0))

            payload = {
                "inputs": [clean[:500]],
                "target_language_code": lang,
                "speaker": speaker,
                "model": model,
                "pace": pace,
                "speech_sample_rate": 22050,
                "enable_preprocessing": True
            }

            req = urllib.request.Request(
                "https://api.sarvam.ai/text-to-speech",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json"
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                audios = data.get("audios", [])
                if not audios:
                    return False
                audio_bytes = base64.b64decode(audios[0])

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_wav:
                f_wav.write(audio_bytes)
                wav_path = f_wav.name

            try:
                player = "pw-play" if shutil.which("pw-play") else "aplay"
                subprocess.run([player, wav_path], timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            finally:
                if os.path.exists(wav_path):
                    try:
                        os.unlink(wav_path)
                    except OSError:
                        pass
        except Exception as e:
            print(f"[omarchy-assistant] Sarvam TTS warning: {e}", file=sys.stderr)
            return False

    def _speak_piper(self, clean: str) -> bool:
        """Synthesize local neural speech via Piper using local ONNX models."""
        piper_bin = shutil.which("piper") or os.path.expanduser("~/.local/bin/piper")
        if not piper_bin or not os.path.exists(piper_bin):
            return False

        # Detect Hindi characters
        has_hindi = any("\u0900" <= c <= "\u097F" for c in clean)
        models_dir = os.path.expanduser("~/.local/share/piper/models")

        if has_hindi:
            model_path = os.path.join(models_dir, "hi_IN-rohan-medium.onnx")
        else:
            model_path = os.path.join(models_dir, "en_US-ryan-medium.onnx")

        # Fallback if specific model not found
        if not os.path.exists(model_path):
            available = [f for f in os.listdir(models_dir) if f.endswith(".onnx")] if os.path.exists(models_dir) else []
            if available:
                model_path = os.path.join(models_dir, available[0])
            else:
                return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_wav:
            wav_path = f_wav.name

        try:
            p = subprocess.Popen(
                [piper_bin, "--model", model_path, "--output-file", wav_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            p.communicate(input=clean, timeout=10)
            if p.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 100:
                player = "pw-play" if shutil.which("pw-play") else "aplay"
                subprocess.run([player, wav_path], timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            return False
        except Exception as e:
            print(f"[omarchy-assistant] Piper TTS error: {e}", file=sys.stderr)
            return False
        finally:
            if os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

    def _speak_worker(self, text: str) -> None:
        """Fetch and play audio over speakers."""
        # Clean text for speech synthesis
        clean = text.replace("`", "").replace("*", "").replace("#", "").strip()
        if not clean:
            return

        # 1. Dedicated Local Engine: Piper TTS (100% offline, zero cloud API)
        if self.backend in ["piper", "local"]:
            if self._speak_piper(clean):
                return

        # 2. Sarvam AI Indian Voices (bulbul:v3 - Aditya, Shubh, Ratan, Kabir)
        if self.backend in ["sarvam", "auto"]:
            if self._speak_sarvam(clean):
                return

        # 3. Piper fallback if backend was auto
        if self.backend == "auto":
            if self._speak_piper(clean):
                return

        # 4. Online fallback: Google TTS via PipeWire / ALSA
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

        # 5. Offline fallback: espeak-ng
        if shutil.which("espeak-ng"):
            try:
                subprocess.run(["espeak-ng", "-s", "175", clean], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

        # 6. Offline fallback: spd-say
        if shutil.which("spd-say"):
            try:
                subprocess.run(["spd-say", clean], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
