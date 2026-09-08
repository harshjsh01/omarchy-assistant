"""
Speech-to-Text (STT) Interactive Testing Utility.
Records microphone audio and displays Whisper transcription in real time
without executing commands or triggering TTS.
"""

import argparse
import os
import sys
import time
import wave
from pathlib import Path

# Add repository root to python path
REPO_DIR = Path(__file__).resolve().parent.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from daemon.config import load_config
from daemon.audio_recorder import AudioRecorder
from daemon.stt_engine import get_stt_engine


# ANSI color formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[1;36m"
C_GREEN = "\033[1;32m"
C_YELLOW = "\033[1;33m"
C_BLUE = "\033[1;34m"
C_RED = "\033[1;31m"
C_DIM = "\033[2m"


def print_banner(engine_name: str, model_info: str, language: str):
    print(f"{C_CYAN}================================================================{C_RESET}")
    print(f" 🎙️  {C_BOLD}Omarchy Voice Assistant — Speech-to-Text (STT) Test{C_RESET}")
    print(f" {C_BLUE}• Engine:{C_RESET} {engine_name}")
    print(f" {C_BLUE}• Model:{C_RESET} {model_info}")
    print(f" {C_BLUE}• Language:{C_RESET} {language} (English, Hindi & Hinglish biased)")
    print(f" {C_DIM}• Mode: Pure STT benchmark (no commands executed, no TTS spoken){C_RESET}")
    print(f"{C_CYAN}================================================================{C_RESET}\n")


def get_audio_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "r") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 0.0


def record_fixed_seconds(recorder: AudioRecorder, seconds: float) -> str:
    """Records audio for a fixed number of seconds using arecord."""
    import subprocess
    import tempfile
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", prefix="omarchy_stt_test_", delete=False)
    tmp_path = tmp_wav.name
    tmp_wav.close()

    print(f"{C_YELLOW}🔴 Recording for {seconds:.1f} seconds... Speak now!{C_RESET}", flush=True)
    cmd = [
        "arecord",
        "-q",
        "-f", "S16_LE",
        "-r", str(recorder.sample_rate),
        "-c", "1",
        "-d", str(int(seconds)),
        tmp_path
    ]
    subprocess.run(cmd, check=True)
    return tmp_path


def run_stt_test_turn(recorder: AudioRecorder, stt, fixed_seconds: float = 0.0) -> bool:
    """Executes a single test turn: records audio and transcribes."""
    wav_path = None
    try:
        if fixed_seconds > 0:
            wav_path = record_fixed_seconds(recorder, fixed_seconds)
        else:
            print(f"{C_GREEN}🎙️  Listening to microphone... Speak now!{C_RESET}")
            print(f"{C_DIM}   (Auto-detects when you finish speaking, or press Ctrl+C to cancel){C_RESET}", flush=True)

            def on_speech_start():
                print(f"   {C_YELLOW}⚡ Speech detected! Continue speaking...{C_RESET}", flush=True)

            wav_path = recorder.record_with_vad(
                max_duration=12.0,
                silence_timeout=1.6,
                energy_threshold=300.0,
                on_speech_start=on_speech_start,
                max_wait_speech=8.0
            )

        if not wav_path or not os.path.exists(wav_path):
            print(f"{C_RED}⚠️  No speech detected. (Check mic volume or speak louder){C_RESET}\n")
            return False

        duration = get_audio_duration(wav_path)
        print(f"\n{C_CYAN}⚙️  Transcribing with Whisper STT ({duration:.2f}s audio)...{C_RESET}", flush=True)

        t0 = time.time()
        transcript = stt.transcribe(wav_path)
        t_transcribe = time.time() - t0

        print(f"\n{C_BOLD}----------------------------------------------------------------{C_RESET}")
        if transcript and transcript.strip():
            print(f" 📝 {C_BOLD}Transcribed Speech:{C_RESET}")
            print(f"    {C_CYAN}\"{transcript}\"{C_RESET}")
        else:
            print(f" ⚠️  {C_YELLOW}[Empty transcription / No distinct words recognized]{C_RESET}")
        print(f"{C_BOLD}----------------------------------------------------------------{C_RESET}")
        print(f" ⏱️  {C_DIM}Audio: {duration:.2f}s | Whisper Latency: {t_transcribe:.2f}s | Speed: {duration / max(0.01, t_transcribe):.1f}x realtime{C_RESET}\n")
        return True

    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Test Omarchy Assistant Speech-to-Text (STT)")
    parser.add_argument("-b", "--backend", "--engine", type=str, default="", help="STT backend to test: sarvam, gemini, whisper-cpp, groq")
    parser.add_argument("-m", "--model", type=str, default="", help="Model name (e.g. saaras:v2, saaras:v3, gemini-2.0-flash, base, small)")
    parser.add_argument("-k", "--key", type=str, default="", help="API key for cloud STT backend (Sarvam/Groq/Gemini)")
    parser.add_argument("-s", "--seconds", type=float, default=0.0, help="Record fixed seconds instead of voice activity detection")
    parser.add_argument("-l", "--loop", action="store_true", help="Keep testing turns continuously until Ctrl+C")
    parser.add_argument("-f", "--file", type=str, default="", help="Transcribe an existing WAV file directly")
    args = parser.parse_args()

    config = load_config()
    if args.backend:
        config["stt_backend"] = args.backend
    if args.model:
        if config.get("stt_backend") == "sarvam":
            config["sarvam_model"] = args.model
        elif config.get("stt_backend") in ["gemini", "gemini-audio"]:
            config["gemini_stt_model"] = args.model
        else:
            config["whisper_model"] = args.model
    if args.key:
        if config.get("stt_backend") == "sarvam":
            config["sarvam_api_key"] = args.key
        elif config.get("stt_backend") in ["gemini", "gemini-audio"]:
            config["gemini_api_key"] = args.key
        elif config.get("stt_backend") == "groq":
            config["groq_api_key"] = args.key

    recorder = AudioRecorder(sample_rate=config.get("sample_rate", 16000))
    stt = get_stt_engine(config)

    engine_name = stt.__class__.__name__
    if engine_name == "SarvamSTTEngine":
        model_name = getattr(stt, "model", "saaras:v2")
    elif engine_name == "GeminiMultimodalSTTEngine":
        model_name = getattr(stt, "model", "gemini-2.0-flash")
    else:
        model_path = getattr(stt, "model_path", "")
        model_name = Path(model_path).name if model_path else getattr(stt, "model_size", "default")
    lang = getattr(stt, "language", getattr(stt, "language_code", "auto"))

    print_banner(engine_name, model_name, lang)

    if engine_name == "SarvamSTTEngine" and not stt.is_available():
        print(f"{C_RED}⚠️  Sarvam API Key is missing!{C_RESET}")
        print(f"{C_YELLOW}To test Sarvam AI ({model_name}):{C_RESET}")
        print(f"  1. Get a free API key at: {C_CYAN}https://dashboard.sarvam.ai/{C_RESET}")
        print(f"  2. Run: {C_CYAN}omarchy-assistant test-stt --backend sarvam --key 'YOUR_API_KEY'{C_RESET}")
        print(f"     Or save it permanently to config: {C_CYAN}omarchy-assistant set-key sarvam 'YOUR_KEY'{C_RESET}\n")
        sys.exit(1)

    # File transcription mode
    if args.file:
        file_path = os.path.expanduser(args.file)
        if not os.path.exists(file_path):
            print(f"{C_RED}Error: File '{file_path}' not found.{C_RESET}")
            sys.exit(1)
        duration = get_audio_duration(file_path)
        print(f"{C_CYAN}⚙️  Transcribing file '{file_path}' ({duration:.2f}s)...{C_RESET}")
        t0 = time.time()
        res = stt.transcribe(file_path)
        t_trans = time.time() - t0
        print(f"\n{C_BOLD}📝 Transcribed Speech:{C_RESET}\n   {C_CYAN}\"{res}\"{C_RESET}\n")
        print(f"{C_DIM}Latency: {t_trans:.2f}s{C_RESET}")
        return

    # Microphone recording mode
    try:
        if args.loop:
            print(f"{C_YELLOW}🔄 Continuous testing loop active. Press Ctrl+C anytime to stop.{C_RESET}\n")
            turn = 1
            while True:
                print(f"{C_BOLD}--- Turn #{turn} ---{C_RESET}")
                run_stt_test_turn(recorder, stt, fixed_seconds=args.seconds)
                turn += 1
                time.sleep(1.0)
        else:
            run_stt_test_turn(recorder, stt, fixed_seconds=args.seconds)
            print(f"{C_DIM}Tip: Run 'omarchy-assistant test-stt --loop' to test multiple phrases in a row.{C_RESET}")
            print(f"{C_DIM}     Run 'omarchy-assistant test-stt --seconds 5' to record exactly 5 seconds.{C_RESET}\n")

    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}STT Test stopped.{C_RESET}")


if __name__ == "__main__":
    main()
