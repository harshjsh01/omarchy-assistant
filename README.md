# 🎙️ Bro (Binary Response Orchestrator) — Omarchy Desktop & AI Assistant

[![Platform](https://img.shields.io/badge/Platform-Omarchy%20Linux%20%7C%20Arch%20Linux-blue?logo=archlinux)](https://omarchy.org/)
[![Window Manager](https://img.shields.io/badge/WM-Hyprland-brightgreen)](https://hyprland.org/)
[![Shell](https://img.shields.io/badge/Shell-Quickshell-purple)](https://quickshell.outfoxxed.me/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Bro** (**B**inary **R**esponse **O**rchestrator) is an autonomous, low-latency conversational desktop AI assistant and voice command system engineered specifically for **Omarchy Linux** (Arch Linux with Hyprland and Quickshell), powered by Google Gemini via Antigravity CLI.

Control your entire operating system using natural speech or text — switch workspaces, launch apps, manage audio and brightness, capture screenshots, dictate text, manage past sessions with semantic memory recall, or execute complex coding workflows.

---

## ✨ Key Capabilities

- **🧠 Autonomous Antigravity Execution (Powered by Gemini)**: Seamlessly executes compound terminal workflows, builds software projects, and manages operating system configurations.
- **🗂️ Antigravity Session Indexing & Semantic Recall (`~/Work/SESSIONS.md`)**: Automatically tracks, indexes, and summarizes all Antigravity CLI sessions. Jump to past sessions naturally (e.g. *"Bro, switch to that session where we played Seedhe Maut"* or `omarchy-assistant sessions switch <id|topic>`).
- **🏎️ Real-World Task Verification & Self-Correction**: Bro verifies every action (e.g. querying `hyprctl clients -j` and active workspaces) to ensure apps actually launch and workspaces switch before confirming completion.
- **🎙️ Hands-Free Continuous Listening**: Wake up Bro hands-free (*"Hey Bro"*, *"Suno Bro"*), speak commands, or put it to sleep (*"Go to sleep"*, *"Chup ho jao"*).
- **🪟 Full Hyprland & Wayland Mastery**: Direct IPC dispatch to switch workspaces, move windows, toggle fullscreen, float windows, and adjust layouts.
- **🎙️ PipeWire Dual-Channel Meeting Transcription**: Simultaneously records mic and speaker call audio, transcribing conversations with executive Markdown summaries in `~/Documents/Omarchy-Transcripts/`.
- **🎨 Native Omarchy Quickshell Plugin**: Animated top-bar widget (`harshjsh01.assistant`) displaying live mic states, floating HUD overlays, and Sarvam Indian TTS feedback.

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

# Antigravity Session Management & Semantic Switching
omarchy-assistant sessions list                    # List all recorded sessions & status
omarchy-assistant sessions current                 # Show active and previous conversation
omarchy-assistant sessions switch <id|topic>       # Semantic or direct jump to a session
omarchy-assistant sessions sync                    # Re-index ~/Work and refresh SESSIONS.md

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
│   ├── session_manager.py         # Session indexer & semantic recall engine
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
