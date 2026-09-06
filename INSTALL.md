# Installation & Configuration Guide

This guide walks you through setting up **Omarchy Voice Assistant** on your Omarchy Linux system.

---

## 1. Prerequisites

Verify you have the required tools installed. Omarchy includes most of these by default:

```bash
# Verify base tools
which python3 arecord wpctl hyprctl brightnessctl wtype wl-copy
```

If any are missing:
```bash
omarchy pkg add alsa-utils wireplumber brightnessctl wtype wl-clipboard
```

---

## 2. Fast Automated Installation

Run the automated installer from the repository:

```bash
cd ~/Work/omarchy-assistant
./setup.sh
```

The installer will:
1. Validate required system utilities.
2. Create default configuration in `~/.config/omarchy-assistant/config.json`.
3. Symlink `omarchy-assistant` to `~/.local/bin/omarchy-assistant`.
4. Validate and install the Quickshell plugin into `~/.config/omarchy/plugins/harshjsh01.assistant`.
5. Enable the status bar widget in Omarchy Shell.
6. Install and start the `omarchy-assistant.service` systemd user daemon.

---

## 3. Configuring Speech Recognition (STT)

Open the configuration file:

```bash
omarchy-assistant config edit
# Or edit directly:
nano ~/.config/omarchy-assistant/config.json
```

### Option A: Ultra-Fast Cloud (Groq Whisper) — **Recommended for speed (<200ms)**

Groq offers free API access to `whisper-large-v3-turbo` with virtually instant response times:

1. Obtain a free API key at [console.groq.com](https://console.groq.com/).
2. In `~/.config/omarchy-assistant/config.json`:
   ```json
   {
     "stt_backend": "groq",
     "groq_api_key": "gsk_your_groq_api_key_here"
   }
   ```
   *Alternatively, export `GROQ_API_KEY` in your shell environment.*

---

### Option B: 100% Offline & Private (Faster-Whisper)

To run entirely locally without internet access or API keys:

1. Install `faster-whisper`:
   ```bash
   pip install faster-whisper
   ```
2. In `~/.config/omarchy-assistant/config.json`:
   ```json
   {
     "stt_backend": "faster-whisper",
     "whisper_model": "base.en",
     "whisper_device": "cpu",
     "whisper_compute_type": "int8"
   }
   ```
   *(If you have an NVIDIA GPU, set `"whisper_device": "cuda"` and `"whisper_compute_type": "float16"` for extreme speed).*

---

### Option C: Zero-Config Google Web Speech API

Free cloud recognition without an API key:

```bash
pip install SpeechRecognition
```

In `~/.config/omarchy-assistant/config.json`:
```json
{
  "stt_backend": "speech_recognition"
}
```

---

## 4. Setting up Hyprland Keybinding

To trigger voice commands with your keyboard, edit your Hyprland bindings file:

```bash
nano ~/.config/hypr/bindings.lua
```

Add this line:
```lua
o.bind("SUPER + A", "Voice Assistant", "omarchy-assistant listen")
```

Hyprland will automatically reload the configuration. Press `SUPER + A` to speak!

---

## 5. Verifying & Testing

### Test via CLI Text Simulation (No microphone needed)

```bash
omarchy-assistant exec "volume up"
omarchy-assistant exec "switch to workspace 2"
omarchy-assistant exec "take screenshot"
```

### Test Voice Recording

```bash
omarchy-assistant listen
# Say "volume 60 percent"
```

### Check Service Status

```bash
omarchy-assistant status
```

---

## 6. Troubleshooting

- **Microphone not picking up audio**:
  Check if your default microphone is unmuted:
  ```bash
  wpctl status
  wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0
  ```
  Test recording directly:
  ```bash
  arecord -d 3 -f S16_LE -r 16000 test.wav && aplay test.wav
  ```

- **Quickshell plugin not showing on bar**:
  Force rescan plugins:
  ```bash
  omarchy-shell shell rescanPlugins
  omarchy restart shell
  ```
