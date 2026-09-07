"""
Intent Parser and Command Router.
Maps spoken natural language phrases to Omarchy Linux actions.
Includes fast regex rules and optional LLM fallback.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, Optional, Tuple


class CommandRouter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def route(self, text: str) -> Dict[str, Any]:
        """
        Parse spoken text and return an action dictionary.
        Returns:
            {
                "status": "matched" | "llm" | "unknown",
                "intent": str,
                "command": str (bash / CLI command to execute),
                "spoken_response": str (feedback to user),
                "category": str
            }
        """
        clean_text = text.lower().strip()
        clean_text = re.sub(r"[^\w\s%+-]", "", clean_text)

        # 1. Direct Regex / Rule Matching
        rule_match = self._match_rules(clean_text)
        if rule_match:
            return rule_match

        # 2. LLM Fallback (if enabled)
        if self.config.get("llm_fallback_enabled", True):
            llm_result = self._fallback_llm(text)
            if llm_result:
                return llm_result

        return {
            "status": "unknown",
            "intent": "unknown",
            "command": "",
            "spoken_response": f"I heard '{text}', but I don't know how to do that.",
            "category": "none"
        }

    def _match_rules(self, text: str) -> Optional[Dict[str, Any]]:
        # --- Audio & Volume ---
        if re.search(r"\b(volume up|increase volume|louder|sound up)\b", text):
            return {
                "status": "matched",
                "intent": "volume_up",
                "command": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
                "spoken_response": "Volume up",
                "category": "audio"
            }
        if re.search(r"\b(volume down|decrease volume|softer|sound down|lower volume)\b", text):
            return {
                "status": "matched",
                "intent": "volume_down",
                "command": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
                "spoken_response": "Volume down",
                "category": "audio"
            }
        m = re.search(r"\b(set volume to|volume)\s*(\d{1,3})\s*(percent|%)?\b", text)
        if m:
            vol = min(100, max(0, int(m.group(2))))
            return {
                "status": "matched",
                "intent": "set_volume",
                "command": f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {vol/100:.2f}",
                "spoken_response": f"Volume set to {vol} percent",
                "category": "audio"
            }
        if re.search(r"\b(mute microphone|mute mic)\b", text):
            return {
                "status": "matched",
                "intent": "mute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1",
                "spoken_response": "Microphone muted",
                "category": "audio"
            }
        if re.search(r"\b(unmute microphone|unmute mic)\b", text):
            return {
                "status": "matched",
                "intent": "unmute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0",
                "spoken_response": "Microphone unmuted",
                "category": "audio"
            }
        if re.search(r"\b(mute audio|mute sound|mute|unmute)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_mute",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
                "spoken_response": "Toggled mute",
                "category": "audio"
            }

        # --- Media Playback ---
        if re.search(r"\b(pause music|pause video|pause playback|pause)\b", text):
            return {
                "status": "matched",
                "intent": "media_pause",
                "command": "playerctl pause 2>/dev/null || true",
                "spoken_response": "Paused",
                "category": "media"
            }
        if re.search(r"\b(play music|resume music|play track|play)\b", text):
            return {
                "status": "matched",
                "intent": "media_play",
                "command": "playerctl play-pause 2>/dev/null || true",
                "spoken_response": "Playing",
                "category": "media"
            }
        if re.search(r"\b(next song|next track|skip song|skip track|next)\b", text):
            return {
                "status": "matched",
                "intent": "media_next",
                "command": "playerctl next 2>/dev/null || true",
                "spoken_response": "Next track",
                "category": "media"
            }
        if re.search(r"\b(previous song|previous track|prev song|previous)\b", text):
            return {
                "status": "matched",
                "intent": "media_previous",
                "command": "playerctl previous 2>/dev/null || true",
                "spoken_response": "Previous track",
                "category": "media"
            }

        # --- Brightness ---
        if re.search(r"\b(brightness up|increase brightness|screen brighter)\b", text):
            return {
                "status": "matched",
                "intent": "brightness_up",
                "command": "brightnessctl set +10%",
                "spoken_response": "Brightness increased",
                "category": "display"
            }
        if re.search(r"\b(brightness down|decrease brightness|screen dimmer)\b", text):
            return {
                "status": "matched",
                "intent": "brightness_down",
                "command": "brightnessctl set 10%-",
                "spoken_response": "Brightness decreased",
                "category": "display"
            }
        m = re.search(r"\b(set brightness to|brightness)\s*(\d{1,3})\s*(percent|%)?\b", text)
        if m:
            bright = min(100, max(5, int(m.group(2))))
            return {
                "status": "matched",
                "intent": "set_brightness",
                "command": f"brightnessctl set {bright}%",
                "spoken_response": f"Brightness set to {bright} percent",
                "category": "display"
            }

        # --- Hyprland Workspaces ---
        m = re.search(r"\b(go to workspace|switch to workspace|workspace)\s*([0-9]|one|two|three|four|five|six|seven|eight|nine|ten)\b", text)
        if m:
            num_map = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                       "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
            raw_target = m.group(2)
            target = num_map.get(raw_target, raw_target)
            return {
                "status": "matched",
                "intent": "switch_workspace",
                "command": f"hyprctl dispatch workspace {target}",
                "spoken_response": f"Switched to workspace {target}",
                "category": "hyprland"
            }

        m = re.search(r"\b(move to workspace|send to workspace)\s*([0-9]|one|two|three|four|five|six|seven|eight|nine|ten)\b", text)
        if m:
            num_map = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                       "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
            raw_target = m.group(2)
            target = num_map.get(raw_target, raw_target)
            return {
                "status": "matched",
                "intent": "move_window_workspace",
                "command": f"hyprctl dispatch movetoworkspace {target}",
                "spoken_response": f"Moved window to workspace {target}",
                "category": "hyprland"
            }

        # --- Hyprland Window Management ---
        if re.search(r"\b(close window|close active window|close this window|kill window|close app)\b", text):
            return {
                "status": "matched",
                "intent": "close_window",
                "command": "hyprctl dispatch killactive",
                "spoken_response": "Closing window",
                "category": "hyprland"
            }
        if re.search(r"\b(fullscreen|toggle fullscreen|full screen)\b", text):
            return {
                "status": "matched",
                "intent": "fullscreen",
                "command": "hyprctl dispatch fullscreen",
                "spoken_response": "Fullscreen toggled",
                "category": "hyprland"
            }
        if re.search(r"\b(float window|floating window|toggle floating|toggle float)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_floating",
                "command": "hyprctl dispatch togglefloating",
                "spoken_response": "Toggled float",
                "category": "hyprland"
            }
        if re.search(r"\b(toggle split|split screen|split orientation)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_split",
                "command": "hyprctl dispatch togglesplit",
                "spoken_response": "Split layout toggled",
                "category": "hyprland"
            }

        # --- Omarchy Theme & Look ---
        m = re.search(r"\b(change theme to|switch theme to|set theme to|theme)\s*([a-zA-Z0-9_-]+)\b", text)
        if m:
            theme_name = m.group(2)
            if theme_name not in ["to", "the", "a", "up", "down", "on", "off"]:
                return {
                    "status": "matched",
                    "intent": "set_theme",
                    "command": f"omarchy theme set {theme_name}",
                    "spoken_response": f"Changing theme to {theme_name}",
                    "category": "omarchy"
                }

        if re.search(r"\b(turn on night light|night light on|enable night light)\b", text):
            return {
                "status": "matched",
                "intent": "nightlight_on",
                "command": "omarchy toggle nightlight",
                "spoken_response": "Night light activated",
                "category": "omarchy"
            }
        if re.search(r"\b(turn off night light|night light off|disable night light)\b", text):
            return {
                "status": "matched",
                "intent": "nightlight_off",
                "command": "omarchy toggle nightlight",
                "spoken_response": "Night light deactivated",
                "category": "omarchy"
            }

        # --- Screenshots & Capture ---
        if re.search(r"\b(take screenshot|screenshot|capture screen|screen shot)\b", text):
            return {
                "status": "matched",
                "intent": "screenshot",
                "command": "omarchy capture screenshot",
                "spoken_response": "Screenshot captured",
                "category": "capture"
            }

        # --- Reminders ---
        m = re.search(r"\b(set reminder|remind me in)\s*(\d+)\s*(minute|minutes|min|mins)?\s*(to|that)?\s*(.*)\b", text)
        if m:
            minutes = m.group(2)
            msg = m.group(5).strip() or "Reminder"
            return {
                "status": "matched",
                "intent": "reminder",
                "command": f"omarchy reminder {minutes} \"{msg}\"",
                "spoken_response": f"Reminder set for {minutes} minutes from now",
                "category": "omarchy"
            }
        if re.search(r"\b(show reminders|view reminders|list reminders)\b", text):
            return {
                "status": "matched",
                "intent": "show_reminders",
                "command": "omarchy reminder show",
                "spoken_response": "Here are your active reminders",
                "category": "omarchy"
            }
        if re.search(r"\b(clear reminders|delete reminders)\b", text):
            return {
                "status": "matched",
                "intent": "clear_reminders",
                "command": "omarchy reminder clear",
                "spoken_response": "Cleared reminders",
                "category": "omarchy"
            }

        # --- Meeting Transcription (Omavoice + Omarvis Dual-Channel Capture) ---
        if re.search(r"\b(start meeting transcription|start meeting record|record meeting|transcribe meeting|join meeting)\b", text):
            return {
                "status": "matched",
                "intent": "start_meeting_transcription",
                "command": "omarchy-assistant meeting start",
                "spoken_response": "Meeting transcription started. Recording your microphone and speaker call audio.",
                "category": "meeting"
            }
        if re.search(r"\b(stop meeting transcription|stop meeting|end meeting|finish meeting|save meeting)\b", text):
            return {
                "status": "matched",
                "intent": "stop_meeting_transcription",
                "command": "omarchy-assistant meeting stop",
                "spoken_response": "Meeting ended. Saving dual-channel transcript to Documents.",
                "category": "meeting"
            }
        if re.search(r"\b(meeting status|is meeting recording)\b", text):
            return {
                "status": "matched",
                "intent": "meeting_status",
                "command": "omarchy-assistant meeting status",
                "spoken_response": "Checking meeting status.",
                "category": "meeting"
            }

        # --- Screen Awareness (Omarvis Feature) ---
        if re.search(r"\b(what is on my screen|summarize my screen|look at my screen|describe my screen)\b", text):
            return {
                "status": "matched",
                "intent": "screen_vision",
                "command": "omarchy capture screenshot && notify-send -a 'Omarchy Assistant' 'Screen Analysis' 'Analyzing active windows and visible content...'",
                "spoken_response": "Analyzing your current screen.",
                "category": "vision"
            }

        # --- Application Launching ---
        if re.search(r"\b(open browser|launch browser|start browser|open chrome|open firefox)\b", text):
            return {
                "status": "matched",
                "intent": "launch_browser",
                "command": "omarchy launch browser",
                "spoken_response": "Opening browser",
                "category": "apps"
            }
        if re.search(r"\b(open terminal|launch terminal|start terminal|new terminal)\b", text):
            return {
                "status": "matched",
                "intent": "launch_terminal",
                "command": "omarchy launch terminal",
                "spoken_response": "Opening terminal",
                "category": "apps"
            }
        if re.search(r"\b(open files|file manager|open nautilus|open file manager)\b", text):
            return {
                "status": "matched",
                "intent": "launch_files",
                "command": "nautilus &",
                "spoken_response": "Opening file manager",
                "category": "apps"
            }
        if re.search(r"\b(open code|launch code|open vscode|launch vscode)\b", text):
            return {
                "status": "matched",
                "intent": "launch_code",
                "command": "code &",
                "spoken_response": "Opening VS Code",
                "category": "apps"
            }
        if re.search(r"\b(open btop|system monitor|task manager)\b", text):
            return {
                "status": "matched",
                "intent": "launch_btop",
                "command": "omarchy launch terminal -e btop &",
                "spoken_response": "Opening system monitor",
                "category": "apps"
            }

        # --- Omarchy System Operations ---
        if re.search(r"\b(lock screen|lock pc|lock computer|lock system)\b", text):
            return {
                "status": "matched",
                "intent": "lock_screen",
                "command": "omarchy system lock",
                "spoken_response": "Locking screen",
                "category": "system"
            }
        if re.search(r"\b(restart shell|reload shell|refresh shell)\b", text):
            return {
                "status": "matched",
                "intent": "refresh_shell",
                "command": "omarchy restart shell",
                "spoken_response": "Restarting Omarchy shell",
                "category": "system"
            }
        if re.search(r"\b(update system|system update)\b", text):
            return {
                "status": "matched",
                "intent": "update_system",
                "command": "omarchy launch terminal -e omarchy update",
                "spoken_response": "Starting Omarchy system update",
                "category": "system"
            }

        # --- Dictation & Typing ---
        m = re.search(r"^(type|write|dictate)\s+(.+)$", text)
        if m:
            dictated_content = m.group(2)
            # Escape for shell safety
            escaped_text = dictated_content.replace("'", "'\\''")
            return {
                "status": "matched",
                "intent": "type_text",
                "command": f"wtype '{escaped_text}'",
                "spoken_response": f"Typed text",
                "category": "dictation"
            }
        m = re.search(r"^(copy to clipboard|copy)\s+(.+)$", text)
        if m:
            copy_content = m.group(2)
            escaped_text = copy_content.replace("'", "'\\''")
            return {
                "status": "matched",
                "intent": "copy_clipboard",
                "command": f"printf '%s' '{escaped_text}' | wl-copy",
                "spoken_response": "Copied to clipboard",
                "category": "clipboard"
            }

        return None

    def _fallback_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Query LLM (Ollama or Groq/OpenAI) to interpret natural instructions."""
        provider = self.config.get("llm_provider", "auto")
        groq_key = self.config.get("groq_api_key") or os.getenv("GROQ_API_KEY")

        system_instruction = (
            "You are Omarchy Assistant, an intelligent voice assistant for Omarchy Linux (Arch Linux with Hyprland). "
            "Given the user's voice command, return a JSON object with: "
            "1. 'command': a safe, single-line bash command to execute (using hyprctl, omarchy, wpctl, playerctl, etc.). "
            "If no OS command is needed, leave empty. "
            "2. 'spoken_response': a short (1-2 sentence) voice response to say to the user. "
            "Return strictly valid JSON only."
        )

        if (provider == "groq" or provider == "auto") and groq_key:
            try:
                payload = {
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return {
                        "status": "llm",
                        "intent": "natural_language_ai",
                        "command": parsed.get("command", ""),
                        "spoken_response": parsed.get("spoken_response", "Done."),
                        "category": "ai"
                    }
            except Exception:
                pass

        # Try local Ollama if running
        try:
            ollama_url = f"{self.config.get('ollama_host', 'http://localhost:11434')}/api/generate"
            ollama_payload = {
                "model": self.config.get("ollama_model", "qwen2.5:3b"),
                "prompt": f"{system_instruction}\n\nUser request: {prompt}\nJSON:",
                "stream": False,
                "format": "json"
            }
            req = urllib.request.Request(
                ollama_url,
                data=json.dumps(ollama_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                content = data.get("response", "{}")
                parsed = json.loads(content)
                return {
                    "status": "llm",
                    "intent": "ollama_ai",
                    "command": parsed.get("command", ""),
                    "spoken_response": parsed.get("spoken_response", "Done."),
                    "category": "ai"
                }
        except Exception:
            pass

        return None
