# Omarchy Voice Assistant — Voice Command Reference

This document catalogs the voice commands supported out-of-the-box by **Omarchy Voice Assistant**.

---

## 🪟 1. Hyprland Workspace Management

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Switch to workspace 2"` / `"Go to workspace 2"` | Switches active workspace | `hyprctl dispatch workspace 2` |
| `"Workspace 5"` | Direct workspace switch | `hyprctl dispatch workspace 5` |
| `"Move to workspace 3"` / `"Send to workspace 3"` | Moves active window to workspace | `hyprctl dispatch movetoworkspace 3` |

*Supports numbers 1 through 10 (digits or words, e.g. "three").*

---

## 🖥️ 2. Hyprland Window Management

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Close window"` / `"Close active window"` / `"Kill window"` | Closes current window | `hyprctl dispatch killactive` |
| `"Fullscreen"` / `"Toggle fullscreen"` | Expands window to fullscreen | `hyprctl dispatch fullscreen` |
| `"Float window"` / `"Toggle floating"` | Toggles floating mode | `hyprctl dispatch togglefloating` |
| `"Toggle split"` / `"Split screen"` | Switches split orientation | `hyprctl dispatch togglesplit` |

---

## 🔊 3. Audio & Volume Control

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Volume up"` / `"Louder"` / `"Increase volume"` | Increases volume by 5% | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+` |
| `"Volume down"` / `"Softer"` / `"Decrease volume"` | Decreases volume by 5% | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-` |
| `"Set volume to 70 percent"` / `"Volume 50%"` | Sets exact volume | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.70` |
| `"Mute"` / `"Mute audio"` / `"Unmute"` | Toggles audio mute | `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle` |
| `"Mute microphone"` / `"Mute mic"` | Mutes microphone | `wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1` |
| `"Unmute microphone"` / `"Unmute mic"` | Unmutes microphone | `wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0` |

---

## 🎵 4. Media Playback

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Play"` / `"Play music"` / `"Resume"` | Resumes media playback | `playerctl play-pause` |
| `"Pause"` / `"Pause music"` / `"Pause video"` | Pauses media playback | `playerctl pause` |
| `"Next song"` / `"Next track"` / `"Skip"` | Advances to next track | `playerctl next` |
| `"Previous song"` / `"Previous track"` | Goes to previous track | `playerctl previous` |

---

## 💡 5. Display & Brightness

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Brightness up"` / `"Screen brighter"` | Increases brightness by 10% | `brightnessctl set +10%` |
| `"Brightness down"` / `"Screen dimmer"` | Decreases brightness by 10% | `brightnessctl set 10%-` |
| `"Set brightness to 80 percent"` | Sets exact brightness level | `brightnessctl set 80%` |
| `"Turn on night light"` / `"Night light on"` | Enables blue light filter | `omarchy toggle nightlight` |
| `"Turn off night light"` / `"Night light off"` | Disables blue light filter | `omarchy toggle nightlight` |

---

## 🎨 6. Omarchy Themes & Styling

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Change theme to catppuccin"` | Switches desktop theme | `omarchy theme set catppuccin` |
| `"Switch theme to nord"` | Switches desktop theme | `omarchy theme set nord` |
| `"Set theme to tokyo-night"` | Switches desktop theme | `omarchy theme set tokyo-night` |
| `"Change theme to gruvbox"` | Switches desktop theme | `omarchy theme set gruvbox` |
| `"Restart shell"` / `"Reload shell"` | Restarts Omarchy Quickshell | `omarchy restart shell` |

---

## ⏰ 7. Capture & Reminders

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Take screenshot"` / `"Capture screen"` | Takes full desktop screenshot | `omarchy capture screenshot` |
| `"Set reminder 15 minutes take medicine"` | Sets desktop reminder | `omarchy reminder 15 "take medicine"` |
| `"Show reminders"` / `"View reminders"` | Displays active reminders | `omarchy reminder show` |
| `"Clear reminders"` | Clears all active reminders | `omarchy reminder clear` |

---

## 🚀 8. Application Launching

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Open browser"` / `"Launch browser"` | Launches default web browser | `omarchy launch browser` |
| `"Open terminal"` / `"Launch terminal"` | Launches default terminal | `omarchy launch terminal` |
| `"Open files"` / `"Open file manager"` | Launches file manager (Nautilus) | `nautilus &` |
| `"Open code"` / `"Launch VS Code"` | Launches Visual Studio Code | `code &` |
| `"Open system monitor"` / `"Open btop"` | Launches btop monitor in terminal | `omarchy launch terminal -e btop &` |

---

## 🔒 9. System Operations

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Lock screen"` / `"Lock computer"` | Locks Wayland session | `omarchy system lock` |
| `"Update system"` | Starts Omarchy system updater | `omarchy launch terminal -e omarchy update` |

---

## ⌨️ 10. Voice Dictation & Clipboard

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Type Hello World"` | Types text into active focused window | `wtype 'Hello World'` |
| `"Write Thank you for your email"` | Types dictated text into window | `wtype '...'` |
| `"Copy to clipboard Meet me at noon"` | Copies text to Wayland clipboard | `printf '%s' '...' \| wl-copy` |

---

## 🎙️ 11. Meeting Transcription (Omavoice + Omarvis Dual Audio)

Captures both **Microphone** (your speech) and **PipeWire System Sink** (remote participants in Zoom, Google Meet, Microsoft Teams, Discord, etc.).

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"Start meeting transcription"` / `"Record meeting"` / `"Join meeting"` | Begins recording local mic + remote speaker streams | `omarchy-assistant meeting start` |
| `"Stop meeting transcription"` / `"Stop meeting"` / `"End meeting"` | Stops recording, generates markdown transcript & AI summary | `omarchy-assistant meeting stop` |
| `"Meeting status"` / `"Is meeting recording"` | Checks if meeting capture is active | `omarchy-assistant meeting status` |

*Meeting transcripts are automatically formatted and saved to `~/Documents/Omarchy-Transcripts/Meeting_<timestamp>.md`.*

---

## 👁️ 12. Screen Vision & Context (Omarvis)

| Voice Command | Action Taken | Subsystem Command |
|---|---|---|
| `"What is on my screen"` / `"Describe my screen"` / `"Summarize my screen"` | Captures screen context and analyzes active window contents | `omarchy capture screenshot` |

---

## 🧠 13. Natural Language & AI Fallback

When a spoken instruction does not match a hardcoded regex pattern, it is automatically handed over to the LLM engine (Ollama local / Groq Cloud / OpenAI).

Examples:
- *"Find all Python files modified today"*
- *"Split screen and open terminal on the right"*
- *"Explain what process is consuming the most memory"*
