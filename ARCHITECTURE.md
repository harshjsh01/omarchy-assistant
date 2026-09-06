# Omarchy Voice Assistant Architecture

This document details the architectural design, communication protocols, and execution lifecycle of **Omarchy Voice Assistant** — the hands-free voice command system for Omarchy Linux (Arch Linux + Hyprland + Quickshell).

---

## 1. High-Level Architecture

The system operates across three tiers:
1. **User Interaction & Wayland UI**: Hyprland push-to-talk hotkeys and Quickshell status bar / HUD overlay.
2. **Core Assistant Daemon**: Python background service managing audio streams, speech recognition (STT), intent routing, and state transitions.
3. **OS Control & Subsystem IPC**: Direct control of Hyprland (`hyprctl`), Omarchy CLI (`omarchy`), audio (`wpctl`), displays (`brightnessctl`), and input synthesis (`wtype`).

```
 +--------------------+       +---------------------------------------------+
 |   Hyprland WM      |       |             Omarchy Quickshell              |
 |   (SUPER + V)      |       |  +--------------------+  +---------------+  |
 +---------+----------+       |  |     BarWidget      |  |  Overlay HUD  |  |
           |                  |  +---------+----------+  +-------+-------+  |
           v                  +------------|---------------------|----------+
 +--------------------+                    |                     |
 | omarchy-assistant  |                    |                     |
 |    CLI Trigger     |                    v                     v
 +---------+----------+       +---------------------------------------------+
           |                  |              omarchy-shell IPC              |
           |                  |       (assistant updateState / trigger)     |
           |                  +----------------------+----------------------+
           v                                         ^
 +---------------------------------------------------|----------------------+
 |                    Omarchy Assistant Daemon (Python)                     |
 |                                                                          |
 |   +--------------------+     +-------------------+     +-------------+   |
 |   |   AudioRecorder    | --> |    STT Engine     | --> |   Command   |   |
 |   | (arecord / VAD)    |     | (Whisper / Groq)  |     |   Router    |   |
 |   +--------------------+     +-------------------+     +------+------+   |
 |                                                               |          |
 |   +-----------------------------------------------------------+          |
 |   |                                                                      |
 |   v                                                                      |
 | +--------------------+       +-------------------+     +-------------+   |
 | |   ActionExecutor   | ----> |    TTS Engine     |     | IPC Server  |   |
 | | (hyprctl / omarchy)|       | (Piper / espeak)  |     | Unix Socket |   |
 | +--------------------+       +-------------------+     +-------------+   |
 +-----------+--------------------------------------------------------------+
             |
             v
 +--------------------------------------------------------------------------+
 |                              Linux Subsystems                            |
 |                                                                          |
 |   • Hyprland IPC (hyprctl dispatch workspace / killactive / fullscreen)  |
 |   • WirePlumber (wpctl set-volume / set-mute)                            |
 |   • Omarchy CLI (omarchy theme / nightlight / reminder / update)         |
 |   • Wayland Input Synthesizer (wtype / wl-copy)                          |
 |   • Hardware Controls (brightnessctl / systemd power)                    |
 +--------------------------------------------------------------------------+
```

---

## 2. Component Breakdown

### A. Core Assistant Daemon (`daemon/`)

- **`main.py`**: Initializes subsystems, coordinates the processing pipeline, handles threading, and prevents race conditions.
- **`audio_recorder.py`**: Interacts with PipeWire/ALSA using `arecord` (or `ffmpeg`). Implements Root Mean Square (RMS) energy analysis for **Voice Activity Detection (VAD)** to automatically stop recording when speech ends.
- **`stt_engine.py`**: Pluggable Speech-to-Text abstraction:
  - *FasterWhisperEngine*: Local offline CTranslate2 inference. Zero network overhead, private, quantized INT8 models for low CPU/GPU usage.
  - *GroqWhisperEngine*: Cloud inference via Groq Whisper Turbo (`whisper-large-v3-turbo`) with round-trip response times under 200ms.
  - *OpenAIWhisperEngine*: Standard OpenAI Whisper API.
  - *SpeechRecognitionEngine*: Zero-config Google Web Speech API.
- **`command_router.py`**: Maps natural speech to structured OS actions:
  - Phase 1: High-speed regular expression and token normalizer (< 1ms).
  - Phase 2: Natural Language Fallback (LLM) for generalized instructions via local Ollama or cloud models.
- **`executor.py`**: Dispatches system calls safely with timeout protection, captures outputs, and triggers desktop notifications.
- **`ipc_server.py`**: Unix Domain Socket (`/tmp/omarchy-assistant.sock`) server processing JSON RPC requests.

---

### B. Omarchy Shell Quickshell Plugin (`plugin/`)

Implements Omarchy's first-class plugin specification:
- **`manifest.json`**: Plugin metadata registering `service` and `bar-widget` entry points. Strictly validated with `omarchy plugin validate`.
- **`Service.qml`**: Background Quickshell service hosting the `assistant` `IpcHandler`. Exposes:
  - `updateState(payloadJson)`: Updates global assistant state (`listening`, `processing`, `executing`, `idle`).
  - `trigger()`: Triggers listening via Quickshell UI.
  - `state()`: Returns current state string.
- **`Overlay.qml`**: Wayland layer-shell HUD overlay (`WlrLayershell.layer: WlrLayer.Overlay`). Renders a centered floating card displaying animated pulsing indicator, transcribed text, and executed action pill.
- **`BarWidget.qml`**: Omarchy status bar icon widget (`󰍬` / `󰚩`) with active pulse states and click-to-speak functionality.

---

## 3. Communication Sequence

```
User               Hyprland            Daemon             STT Engine       OS Subsystem      Quickshell HUD
 │                     │                  │                   │                 │                  │
 │─ [Press Super+V] ──>│                  │                   │                 │                  │
 │                     │── omarchy-listen>│                   │                 │                  │
 │                     │                  │── updateState("listening") ─────────┼─────────────────>│ (Show HUD)
 │                     │                  │                   │                 │                  │
 │─ [Speak command] ─────────────────────>│                   │                 │                  │
 │   "volume 70%"                         │                   │                 │                  │
 │                                        │ (Silence detected)│                 │                  │
 │                                        │── WAV bytes ─────>│                 │                  │
 │                                        │<─ "volume 70%" ───│                 │                  │
 │                                        │                                     │                  │
 │                                        │── updateState("executing") ─────────┼─────────────────>│ (Update HUD)
 │                                        │                                     │                  │
 │                                        │── wpctl set-volume 0.70 ───────────>│                  │
 │                                        │<─ OK ───────────────────────────────│                  │
 │                                        │                                                        │
 │                                        │── updateState("idle") ──────────────┼─────────────────>│ (Fade out)
 v                                        v                                     v                  v
```

---

## 4. Latency Characteristics

| Pipeline Stage | Engine | Average Latency |
|---|---|---|
| Audio Capture & VAD | Native PipeWire/ALSA | Real-time + 300ms silence margin |
| Speech-to-Text | Groq Cloud API | ~120ms - 180ms |
| Speech-to-Text | Local Faster-Whisper (CPU int8) | ~400ms - 750ms |
| Command Routing | Regex Pattern Engine | < 2ms |
| OS Execution | `wpctl` / `hyprctl` / `omarchy` | ~10ms - 50ms |
| UI Update | Quickshell Layer-shell IPC | < 15ms |
| **Total End-to-End** | **Cloud (Groq)** | **~500ms** |
| **Total End-to-End** | **Local (Faster-Whisper)** | **~850ms** |

---

## 5. Security & Safety Principles

1. **Restricted Sockets**: The Unix domain socket `/tmp/omarchy-assistant.sock` is created with permissions `0660`, restricting access exclusively to the active user session.
2. **Input Sanitization**: Variables passed into shell commands (such as typing or clipboard content) are escaped to prevent arbitrary command injection.
3. **No Sudo Elevation**: All desktop voice commands run in unprivileged user space. Privileged operations (such as system updates) invoke standard interactive terminals or polkit prompts.
