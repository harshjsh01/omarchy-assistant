# 🎙️ Omarchy Voice Assistant

[![Platform](https://img.shields.io/badge/Platform-Omarchy%20Linux%20%7C%20Arch%20Linux-blue?logo=archlinux)](https://omarchy.org/)
[![Window Manager](https://img.shields.io/badge/WM-Hyprland-brightgreen)](https://hyprland.org/)
[![Shell](https://img.shields.io/badge/Shell-Quickshell-purple)](https://quickshell.outfoxxed.me/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Omarchy Voice Assistant** is an intelligent, low-latency voice command system and AI assistant engineered specifically for **Omarchy Linux** (Arch Linux with Hyprland and Quickshell).

Control your entire operating system using natural speech — switch workspaces, launch apps, manage audio and brightness, toggle themes, capture screenshots, dictate text into active windows, or chat with local/cloud LLMs.

---

## ✨ Features

- **🏎️ Sub-Second Voice Control**: Instant execution (<500ms) with lightweight audio capture and Voice Activity Detection (VAD).
- **🪟 Full Hyprland & Wayland Mastery (Omarvis Core)**: Direct IPC dispatch to switch workspaces, move windows, toggle fullscreen, float windows, and adjust layouts.
- **🎙️ PipeWire Dual-Channel Meeting Transcription (Omavoice Integration)**:
  - Simultaneously captures **local microphone** (you) and **system speaker output** (remote participants in Zoom, Google Meet, Microsoft Teams, Discord).
  - Generates timestamped Markdown transcripts and AI executive summaries directly in `~/Documents/Omarchy-Transcripts/`.
  - Start/stop via voice (`"start meeting transcription"` / `"stop meeting"`) or hotkey (`SUPER + ALT + A`).
- **🎨 Native Omarchy Quickshell Plugin**:
  - **Animated Status Bar Widget**: Displays live microphone states (`󰍬` idle, listening, thinking, executing, recording).
  - **Heads-Up Display (HUD) Overlay**: Floating visual card showing live speech transcripts, animated audio waves, and action badges.
- **🔌 Multi-Engine Speech Recognition (STT)**:
  - **Offline Local**: `faster-whisper` (CTranslate2 INT8 quantized models) for 100% private, offline use.
  - **Ultra-Fast Cloud**: Groq Cloud API (`whisper-large-v3-turbo`) with response times under ~180ms.
  - **Zero-Config Cloud**: OpenAI Whisper API or Google Web Speech API.
- **👁️ Screen & Context Awareness**: Ask `"What is on my screen?"` to trigger instant Wayland screenshot capture and visual analysis.
- **⌨️ Voice Dictation & Input Synthesis**: Speak `"Type Hello World"` or `"Copy my email"` to inject keystrokes into any active Wayland window via `wtype` and `wl-copy`.
- **🧠 Natural Language AI Fallback**: Complex requests are seamlessly routed to local **Ollama** or cloud LLMs to translate intent into shell commands.

---

## 🏗️ Architecture

```
[Voice Input / Mic] ──> [AudioRecorder + VAD] ──> [STT Engine (Whisper/Groq)]
                                                              │
                                                              v
[Quickshell HUD / Bar] <── [IPC Server / Socket] <── [Command Router & LLM]
                                                              │
                                                              v
                                                    [Action Executor]
                                                              │
                     ┌───────────────────────┬────────────────┴───────────────────────┐
                     ▼                       ▼                                        ▼
             [Hyprland IPC]            [Omarchy CLI]                            [Wayland Tools]
           (workspaces, tiling)     (themes, nightlight)                       (wtype, wl-copy)
```

For complete technical specifications, review [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and run the automated installer:

```bash
git clone https://github.com/harshjsh01/omarchy-assistant.git ~/Work/omarchy-assistant
cd ~/Work/omarchy-assistant
./setup.sh
```

### 2. Configure Speech Backend

Edit `~/.config/omarchy-assistant/config.json`:

```json
{
  "stt_backend": "auto",
  "whisper_model": "base.en",
  "groq_api_key": "YOUR_GROQ_KEY_IF_USING_CLOUD"
}
```

*(See [INSTALL.md](INSTALL.md) for full configuration options, including offline local Whisper).*

### 3. Add Keybindings to Hyprland
 
Add these lines to `~/.config/hypr/bindings.lua`:
 
```lua
-- Voice Assistant HUD
o.bind("SUPER + A", "Voice Assistant", "/home/rio_krishna/.local/bin/omarchy-assistant listen")

-- Toggle Two-Way Meeting Recording (Mic + Call Participants)
o.bind("SUPER + ALT + A", "Toggle Meeting Transcription", "/home/rio_krishna/.local/bin/omarchy-assistant meeting start")
```

*(Note: `SUPER + V` is left completely intact as your universal clipboard manager).*

---

## 🗣️ Common Voice Commands

| Category | Example Phrases |
|---|---|
| **Workspaces** | *"Switch to workspace 2"*, *"Move to workspace 4"*, *"Workspace 1"* |
| **Window Control** | *"Close window"*, *"Toggle fullscreen"*, *"Float window"*, *"Split screen"* |
| **Meetings** | *"Start meeting transcription"*, *"Stop meeting"*, *"Meeting status"* |
| **Screen Vision** | *"What is on my screen?"*, *"Describe my screen"* |
| **Volume & Audio** | *"Volume up"*, *"Volume 70 percent"*, *"Mute"*, *"Mute mic"*, *"Unmute mic"* |
| **Media Playback** | *"Play"*, *"Pause"*, *"Next track"*, *"Previous song"* |
| **Display & Look** | *"Brightness up"*, *"Screen 80%"*, *"Turn on night light"*, *"Change theme to catppuccin"* |
| **Omarchy Tools** | *"Take screenshot"*, *"Set reminder in 15 minutes take medicine"*, *"Reload shell"* |
| **Apps** | *"Open browser"*, *"Open terminal"*, *"Open files"*, *"Open VS Code"*, *"Open system monitor"* |
| **Dictation** | *"Type meeting notes"*, *"Copy my confirmation code"* |
| **System** | *"Lock screen"*, *"Update system"* |

*Explore the full command dictionary in [COMMANDS.md](COMMANDS.md).*

---

## 🛠️ CLI Usage

```bash
# Push-to-talk trigger
omarchy-assistant listen

# Meeting Transcription (Dual-channel: Mic + Speaker call audio)
omarchy-assistant meeting start    # Begins recording both streams
omarchy-assistant meeting status   # Checks active recording duration
omarchy-assistant meeting stop     # Stops, transcribes, and saves to ~/Documents/Omarchy-Transcripts/
omarchy-assistant meeting list     # Lists saved meeting notes

# Simulate or test command via text
omarchy-assistant exec "switch to workspace 3"
omarchy-assistant exec "volume 80%"

# Check service and socket status
omarchy-assistant status

# Manage systemd background service
omarchy-assistant service status
omarchy-assistant service restart
```

---

## 📂 Project Structure

```
omarchy-assistant/
├── bin/
│   └── omarchy-assistant          # User CLI tool and keybinding target
├── config/
│   └── config.json                # Default configuration
├── daemon/
│   ├── main.py                    # Main daemon entrypoint
│   ├── audio_recorder.py          # PipeWire/ALSA capture with VAD
│   ├── stt_engine.py              # Modular STT engines (Whisper, Groq)
│   ├── command_router.py          # Intent parser & regex engine
│   ├── executor.py                # OS command execution & notifications
│   ├── ipc_server.py              # Unix domain socket server
│   └── tts_engine.py              # Optional voice feedback
├── plugin/
│   ├── manifest.json              # Omarchy shell plugin manifest
│   ├── Service.qml                # Quickshell service & IPC handler
│   ├── BarWidget.qml              # Status bar microphone widget
│   └── Overlay.qml                # Layer-shell HUD overlay
├── hyprland/
│   └── bindings-assistant.lua     # Hyprland bindings snippet
├── systemd/
│   └── omarchy-assistant.service  # systemd user service
├── setup.sh                       # One-click installer & validator
├── ARCHITECTURE.md                # System design & protocol docs
├── COMMANDS.md                    # Voice command reference
└── INSTALL.md                     # Detailed installation guide
```

---

## 📄 License

Distributed under the [MIT License](LICENSE). Developed for the Omarchy Linux community by Harsh Joshi.
