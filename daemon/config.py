"""
Configuration management for Omarchy Voice Assistant.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "omarchy-assistant"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path.home() / ".cache" / "omarchy-assistant"
SOCKET_PATH = "/tmp/omarchy-assistant.sock"

DEFAULT_CONFIG: Dict[str, Any] = {
    # Speech-to-Text configuration
    # Options: "auto", "faster-whisper", "groq", "openai", "speech_recognition", "vosk", "mock"
    "stt_backend": "auto",
    "whisper_model": "base.en",
    "whisper_device": "cpu",       # "cpu" or "cuda"
    "whisper_compute_type": "int8", # "int8", "float16", "default"

    # API Keys (can also be read from environment variables)
    "groq_api_key": "",
    "openai_api_key": "",
    "gemini_api_key": "",

    # Audio recording settings
    "sample_rate": 16000,
    "max_record_seconds": 12,
    "silence_threshold_energy": 300,
    "silence_duration_seconds": 1.2,
    "min_record_seconds": 0.8,

    # Text-to-Speech & Feedback
    "tts_enabled": False,
    "tts_backend": "auto",          # "auto", "piper", "espeak-ng", "none"
    "sound_feedback": True,         # Play start/stop chimes
    "notify_osd": True,             # Show desktop notifications

    # Natural Language / LLM Fallback
    "llm_fallback_enabled": True,
    "llm_provider": "auto",         # "auto", "ollama", "groq", "gemini", "openai"
    "ollama_model": "qwen2.5:3b",
    "ollama_host": "http://localhost:11434",

    # UI / Overlay
    "show_overlay": True,
    "overlay_timeout_seconds": 4.0,

    # Keybinding hint
    "hotkey": "SUPER + A"
}


def load_config() -> Dict[str, Any]:
    """Load configuration with fallback to defaults."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"[omarchy-assistant] Warning: Failed to parse {CONFIG_FILE}: {e}")

    # Override from environment variables if present
    if os.getenv("GROQ_API_KEY") and not config.get("groq_api_key"):
        config["groq_api_key"] = os.getenv("GROQ_API_KEY", "")
    if os.getenv("OPENAI_API_KEY") and not config.get("openai_api_key"):
        config["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
    if os.getenv("GEMINI_API_KEY") and not config.get("gemini_api_key"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")

    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
