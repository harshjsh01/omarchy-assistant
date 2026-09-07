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
        # Direct wake call or greeting to Max
        if re.search(r"^(hey\s+max|ok\s+max|hello\s+max|hi\s+max|max|arrey\s+max)\b$", clean_text):
            return {
                "status": "matched",
                "intent": "greeting",
                "command": "",
                "spoken_response": "Yes, I am live. How may I assist you today?",
                "category": "conversational"
            }

        # Strip wake prefix (e.g. "Max open browser" -> "open browser")
        clean_text = re.sub(r"^(hey\s+max|ok\s+max|hello\s+max|hi\s+max|max|arrey\s+max)\b\s*", "", clean_text).strip()
        normalized_text = re.sub(r"[^\w\s%+-]", "", clean_text)

        # 1. Direct Regex / Rule Matching
        rule_match = self._match_rules(normalized_text)
        if rule_match:
            return rule_match

        # 2. Conversational & LLM Fallback
        if self.config.get("llm_fallback_enabled", True):
            llm_result = self._fallback_llm(clean_text or text)
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
        # --- Audio & Volume (English + Hindi/Hinglish) ---
        if re.search(r"\b(volume up|increase volume|louder|sound up|aa?wa?a?[zj] badhao|volume badhao|aa?wa?a?[zj] badha do|aawaz badhao)\b", text):
            return {
                "status": "matched",
                "intent": "volume_up",
                "command": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
                "spoken_response": "Volume up",
                "category": "audio"
            }
        if re.search(r"\b(volume down|decrease volume|softer|sound down|lower volume|aa?wa?a?[zj] kam karo|volume kam karo|aa?wa?a?[zj] dheemi karo|aawaz kam karo)\b", text):
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
        if re.search(r"\b(mute microphone|mute mic|mic band karo|mike band karo|mic mute karo)\b", text):
            return {
                "status": "matched",
                "intent": "mute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1",
                "spoken_response": "Microphone muted",
                "category": "audio"
            }
        if re.search(r"\b(unmute microphone|unmute mic|mic chalu karo|mic on karo|unmute mic karo)\b", text):
            return {
                "status": "matched",
                "intent": "unmute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0",
                "spoken_response": "Microphone unmuted",
                "category": "audio"
            }
        if re.search(r"\b(mute audio|mute sound|mute|unmute|aa?wa?a?[zj] band karo|chup karo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_mute",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
                "spoken_response": "Toggled mute",
                "category": "audio"
            }

        # --- Media Playback (English + Hindi/Hinglish) ---
        if re.search(r"\b(pause music|pause video|pause playback|pause|gaana roko|gana roko|roko)\b", text):
            return {
                "status": "matched",
                "intent": "media_pause",
                "command": "playerctl pause 2>/dev/null || true",
                "spoken_response": "Paused",
                "category": "media"
            }
        if re.search(r"\b(play music|resume music|play track|play|gaana bajao|gana bajao|gaana chalao|gana chalao)\b", text):
            return {
                "status": "matched",
                "intent": "media_play",
                "command": "playerctl play-pause 2>/dev/null || true",
                "spoken_response": "Playing",
                "category": "media"
            }
        if re.search(r"\b(next song|next track|skip song|skip track|next|agla gaana|agla gana)\b", text):
            return {
                "status": "matched",
                "intent": "media_next",
                "command": "playerctl next 2>/dev/null || true",
                "spoken_response": "Next track",
                "category": "media"
            }
        if re.search(r"\b(previous song|previous track|prev song|previous|pichhla gaana|pichhla gana)\b", text):
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

        # --- Hyprland Workspaces (English + Hindi/Hinglish) ---
        m = re.search(r"\b(go to workspace|switch to workspace|workspace|workspace par jao|workspace number)\s*([0-9]|one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|paanch|chhe|saat|aath|nau|dus)\b", text)
        if m:
            num_map = {
                "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
                "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5",
                "chhe": "6", "saat": "7", "aath": "8", "nau": "9", "dus": "10"
            }
            raw_target = m.group(2)
            target = num_map.get(raw_target, raw_target)
            return {
                "status": "matched",
                "intent": "switch_workspace",
                "command": f"hyprctl dispatch 'hl.dsp.focus({{ workspace = \"{target}\" }})'",
                "spoken_response": f"Switched to workspace {target}",
                "category": "hyprland"
            }

        m = re.search(r"\b(move to workspace|send to workspace|workspace par bhejo)\s*([0-9]|one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|paanch|chhe|saat|aath|nau|dus)\b", text)
        if m:
            num_map = {
                "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
                "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5",
                "chhe": "6", "saat": "7", "aath": "8", "nau": "9", "dus": "10"
            }
            raw_target = m.group(2)
            target = num_map.get(raw_target, raw_target)
            return {
                "status": "matched",
                "intent": "move_window_workspace",
                "command": f"hyprctl dispatch 'hl.dsp.window.move({{ workspace = \"{target}\" }})'",
                "spoken_response": f"Moved window to workspace {target}",
                "category": "hyprland"
            }

        # --- Hyprland Window Management (English + Hindi/Hinglish) ---
        if re.search(r"\b(close window|close active window|close this window|kill window|close app|window band karo|ye window band karo|isko band karo|band karo)\b", text):
            return {
                "status": "matched",
                "intent": "close_window",
                "command": "bash -c 'if ! hyprctl activewindow | grep -q \"class: org.omarchy.agent\"; then hyprctl dispatch \"hl.dsp.window.close()\"; else notify-send -a \"Omarchy Voice Assistant\" -i dialog-warning \"Protected Window\" \"Refusing to close active Antigravity Agent chat session\"; fi'",
                "spoken_response": "Closing window",
                "category": "hyprland"
            }
        if re.search(r"\b(fullscreen|toggle fullscreen|full screen|badi screen karo|fullscreen karo|bada karo)\b", text):
            return {
                "status": "matched",
                "intent": "fullscreen",
                "command": "hyprctl dispatch 'hl.dsp.window.fullscreen({ mode = \"fullscreen\" })'",
                "spoken_response": "Fullscreen toggled",
                "category": "hyprland"
            }
        if re.search(r"\b(float window|floating window|toggle floating|toggle float|float karo|floating karo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_floating",
                "command": "hyprctl dispatch 'hl.dsp.window.float({ action = \"toggle\" })'",
                "spoken_response": "Toggled float",
                "category": "hyprland"
            }
        if re.search(r"\b(toggle split|split screen|split orientation|screen split karo|split karo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_split",
                "command": "hyprctl dispatch 'hl.dsp.layout(\"togglesplit\")'",
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

        # --- Screenshots & Capture (English + Hindi/Hinglish) ---
        if re.search(r"\b(take screenshot|screenshot|capture screen|screen shot|screenshot lo|photo kheencho|screen capture karo|screenshot kheencho)\b", text):
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

        # --- Meeting Transcription (Omavoice + Omarvis Dual-Channel Capture - English + Hindi) ---
        if re.search(r"\b(start meeting transcription|start meeting record|record meeting|transcribe meeting|join meeting|meeting record karo|meeting shuru karo|meeting start karo)\b", text):
            return {
                "status": "matched",
                "intent": "start_meeting_transcription",
                "command": "omarchy-assistant meeting start",
                "spoken_response": "Meeting transcription started. Recording your microphone and speaker call audio.",
                "category": "meeting"
            }
        if re.search(r"\b(stop meeting transcription|stop meeting|end meeting|finish meeting|save meeting|meeting band karo|meeting khatam karo|meeting roko)\b", text):
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

        # --- Screen Awareness (Omarvis Feature - English + Hindi) ---
        if re.search(r"\b(what is on my screen|summarize my screen|look at my screen|describe my screen|screen par kya hai|screen dekh ke batao|screen par dekho)\b", text):
            return {
                "status": "matched",
                "intent": "screen_vision",
                "command": "omarchy capture screenshot && notify-send -a 'Omarchy Assistant' 'Screen Analysis' 'Analyzing active windows and visible content...'",
                "spoken_response": "Analyzing your current screen.",
                "category": "vision"
            }

        # --- Application Launching (English + Hindi/Hinglish) ---
        if re.search(r"\b(open browser|launch browser|start browser|open chrome|open firefox|browser kholo|browser open karo|chrome kholo|internet kholo|browser chalao)\b", text):
            return {
                "status": "matched",
                "intent": "launch_browser",
                "command": "omarchy launch browser",
                "spoken_response": "Opening browser",
                "category": "apps"
            }
        if re.search(r"\b(open terminal|launch terminal|start terminal|new terminal|terminal kholo|terminal open karo|naya terminal|terminal chalao|terminal start karo)\b", text):
            return {
                "status": "matched",
                "intent": "launch_terminal",
                "command": "omarchy launch terminal",
                "spoken_response": "Opening terminal",
                "category": "apps"
            }
        if re.search(r"\b(open files|file manager|open nautilus|open file manager|files kholo|file manager kholo)\b", text):
            return {
                "status": "matched",
                "intent": "launch_files",
                "command": "nautilus &",
                "spoken_response": "Opening file manager",
                "category": "apps"
            }
        if re.search(r"\b(open code|launch code|open vscode|launch vscode|vs code kholo|code kholo)\b", text):
            return {
                "status": "matched",
                "intent": "launch_code",
                "command": "code &",
                "spoken_response": "Opening VS Code",
                "category": "apps"
            }
        if re.search(r"\b(open btop|system monitor|task manager|monitor kholo)\b", text):
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

        # --- Omarchy Menus & Shortcuts (SUPER + K Keybindings Table) ---
        if re.search(r"\b(keybindings|shortcuts|shortcut menu|keys menu|saare shortcuts)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_keybindings",
                "command": "omarchy-menu toggle keybindings",
                "spoken_response": "Opening Omarchy keybindings reference",
                "category": "omarchy"
            }
        if re.search(r"\b(omarchy menu|root menu|main menu|start menu)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_root_menu",
                "command": "omarchy-menu toggle root",
                "spoken_response": "Opening Omarchy menu",
                "category": "omarchy"
            }
        if re.search(r"\b(system menu|system options)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_system_menu",
                "command": "omarchy-menu toggle system",
                "spoken_response": "Opening system menu",
                "category": "omarchy"
            }
        if re.search(r"\b(theme menu|change style|style menu)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_theme_menu",
                "command": "omarchy-menu toggle theme",
                "spoken_response": "Opening theme selector",
                "category": "omarchy"
            }
        if re.search(r"\b(clipboard manager|clipboard history|clipboard kholo|paste history)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_clipboard_menu",
                "command": "omarchy-menu toggle clipboard",
                "spoken_response": "Opening clipboard manager",
                "category": "omarchy"
            }
        if re.search(r"\b(emoji picker|emojis|emoji menu)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_emoji_menu",
                "command": "omarchy-menu toggle emoji",
                "spoken_response": "Opening emoji picker",
                "category": "omarchy"
            }
        if re.search(r"\b(open calculator|calculator|calculator kholo|hisab kitab)\b", text):
            return {
                "status": "matched",
                "intent": "launch_calculator",
                "command": "omarchy-menu toggle calculator || gnome-calculator &",
                "spoken_response": "Opening calculator",
                "category": "apps"
            }
        if re.search(r"\b(wifi menu|network menu|network settings|wifi kholo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_wifi_menu",
                "command": "omarchy-menu toggle wifi",
                "spoken_response": "Opening network menu",
                "category": "omarchy"
            }
        if re.search(r"\b(bluetooth menu|bluetooth settings|bluetooth kholo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_bluetooth_menu",
                "command": "omarchy-menu toggle bluetooth",
                "spoken_response": "Opening Bluetooth menu",
                "category": "omarchy"
            }
        if re.search(r"\b(audio menu|sound settings|volume menu)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_audio_menu",
                "command": "omarchy-menu toggle audio",
                "spoken_response": "Opening audio settings",
                "category": "omarchy"
            }
        if re.search(r"\b(power menu|shutdown menu|log out menu)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_power_menu",
                "command": "omarchy-menu toggle power",
                "spoken_response": "Opening power options",
                "category": "omarchy"
            }
        if re.search(r"\b(wallpapers|change wallpaper|wallpaper menu|background switcher)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_wallpaper_menu",
                "command": "omarchy-menu toggle wallpaper",
                "spoken_response": "Opening wallpaper switcher",
                "category": "omarchy"
            }
        if re.search(r"\b(toggle gaps|toggle window gaps|gaps toggle|gaps band karo|gaps chalu karo)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_gaps",
                "command": "omarchy toggle gaps 2>/dev/null || true",
                "spoken_response": "Toggled window gaps",
                "category": "hyprland"
            }
        if re.search(r"\b(toggle bar|toggle top bar|hide bar|show bar)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_bar",
                "command": "omarchy-shell bar toggle 2>/dev/null || true",
                "spoken_response": "Toggled top bar",
                "category": "omarchy"
            }
        if re.search(r"\b(notification center|notifications|show notifications|open notifications)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_notifications",
                "command": "omarchy-shell rio_krishna.notifications toggle 2>/dev/null || true",
                "spoken_response": "Toggled notification center",
                "category": "omarchy"
            }
        if re.search(r"\b(task overview|overview|hyprtasking|tasks overview)\b", text):
            return {
                "status": "matched",
                "intent": "toggle_overview",
                "command": "hyprctl dispatch 'hl.plugin.hyprtasking.toggle(\"cursor\")'",
                "spoken_response": "Toggled task overview",
                "category": "hyprland"
            }
        if re.search(r"\b(open youtube|youtube kholo|play youtube)\b", text):
            return {
                "status": "matched",
                "intent": "open_youtube",
                "command": "omarchy launch browser https://youtube.com",
                "spoken_response": "Opening YouTube",
                "category": "apps"
            }
        if re.search(r"\b(open whatsapp|whatsapp kholo)\b", text):
            return {
                "status": "matched",
                "intent": "open_whatsapp",
                "command": "omarchy launch browser https://web.whatsapp.com",
                "spoken_response": "Opening WhatsApp",
                "category": "apps"
            }
        if re.search(r"\b(open twitter|open x|x kholo)\b", text):
            return {
                "status": "matched",
                "intent": "open_twitter",
                "command": "omarchy launch browser https://x.com",
                "spoken_response": "Opening X",
                "category": "apps"
            }
        if re.search(r"\b(open calendar|calendar kholo)\b", text):
            return {
                "status": "matched",
                "intent": "open_calendar",
                "command": "omarchy launch browser https://calendar.google.com",
                "spoken_response": "Opening Google Calendar",
                "category": "apps"
            }
        if re.search(r"\b(open email|open gmail|mail kholo)\b", text):
            return {
                "status": "matched",
                "intent": "open_email",
                "command": "omarchy launch browser https://mail.google.com",
                "spoken_response": "Opening Gmail",
                "category": "apps"
            }
        if re.search(r"\b(open obsidian|obsidian kholo)\b", text):
            return {
                "status": "matched",
                "intent": "open_obsidian",
                "command": "obsidian &",
                "spoken_response": "Opening Obsidian",
                "category": "apps"
            }

        # --- Continuous Listening Commands ---
        if re.search(r"\b(start continuous listening|continuous mode|keep listening|always listen|continuous suno)\b", text):
            return {
                "status": "matched",
                "intent": "start_continuous",
                "command": "omarchy-assistant continuous start",
                "spoken_response": "Continuous listening mode activated. I am listening freely, say stop listening when you want me to sleep.",
                "category": "assistant"
            }
        if re.search(r"\b(stop continuous listening|stop listening|chup ho jao|go to sleep|sleep now|chup raho)\b", text):
            return {
                "status": "matched",
                "intent": "stop_continuous",
                "command": "omarchy-assistant continuous stop",
                "spoken_response": "Going to sleep. Press Super plus A or say Hey Max whenever you need me.",
                "category": "assistant"
            }

        # --- Dictation & Typing ---
        m = re.search(r"^(type|write|dictate)\s+(.+)$", text)
        if m:
            dictated_content = m.group(2)
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
        """Conversational AI engine for Max (offline smart rules + LLM)."""
        clean = prompt.lower().strip()

        # 1. Identity & Persona (Max)
        if re.search(r"\b(who are you|tum kaun ho|what is your name|apna naam batao|tell me about yourself)\b", clean):
            return {
                "status": "llm",
                "intent": "persona_identity",
                "command": "",
                "spoken_response": "I am Max, your personal voice assistant for Omarchy Linux. I can control your desktop, workspaces, windows, launch apps, record meetings, and answer your questions.",
                "category": "ai"
            }
        if re.search(r"\b(what can you do|tum kya kar sakte ho|help me|features)\b", clean):
            return {
                "status": "llm",
                "intent": "persona_capabilities",
                "command": "",
                "spoken_response": "You can ask me to open apps, switch workspaces, control volume and media, take screenshots, record meetings with transcription, or answer any question.",
                "category": "ai"
            }
        if re.search(r"\b(how are you|kaise ho|kya haal hai)\b", clean):
            return {
                "status": "llm",
                "intent": "smalltalk_status",
                "command": "",
                "spoken_response": "I am running at peak performance and ready to assist you!",
                "category": "ai"
            }
        if re.search(r"\b(tell me a joke|koi joke sunao|make me laugh)\b", clean):
            jokes = [
                "Why do Linux users love the dark? Because light attracts bugs!",
                "There are 10 types of people in the world: those who understand binary, and those who don't.",
                "Why did the developer go broke? Because he used up all his cache!"
            ]
            import random
            return {
                "status": "llm",
                "intent": "joke",
                "command": "",
                "spoken_response": random.choice(jokes),
                "category": "ai"
            }

        # 2. Time and Date Queries
        if re.search(r"\b(what time is it|time kya hai|kya time hua hai|current time)\b", clean):
            import datetime
            now_str = datetime.datetime.now().strftime("%I:%M %p")
            return {
                "status": "llm",
                "intent": "current_time",
                "command": "",
                "spoken_response": f"It is currently {now_str}.",
                "category": "ai"
            }
        if re.search(r"\b(what is today's date|today's date|aaj kaunsi tareekh hai|current date)\b", clean):
            import datetime
            now_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
            return {
                "status": "llm",
                "intent": "current_date",
                "command": "",
                "spoken_response": f"Today is {now_str}.",
                "category": "ai"
            }

        # 3. Math & Quick Calculations
        calc_match = re.search(r"(?:what is|calculate|solve)?\s*(\d+(?:\.\d+)?\s*[\+\-\*\/xX]\s*\d+(?:\.\d+)?)\b", clean)
        if calc_match:
            expr = calc_match.group(1).replace("x", "*").replace("X", "*")
            try:
                # Safe evaluation of basic math
                val = eval(expr, {"__builtins__": None}, {})
                return {
                    "status": "llm",
                    "intent": "calculator",
                    "command": "",
                    "spoken_response": f"The answer is {val}.",
                    "category": "ai"
                }
            except Exception:
                pass

        # 4. System Specs & Battery
        if re.search(r"\b(battery|battery level|battery percentage)\b", clean):
            return {
                "status": "llm",
                "intent": "battery_status",
                "command": "upower -i $(upower -e | grep 'BAT') 2>/dev/null | grep -E 'percentage|state' || echo 'No battery found'",
                "spoken_response": "Checking battery status.",
                "category": "system"
            }

        # 5. Cloud LLM (Groq / Ollama / OpenAI) if configured
        provider = self.config.get("llm_provider", "auto")
        groq_key = self.config.get("groq_api_key") or os.getenv("GROQ_API_KEY")

        system_instruction = (
            "You are Max, an ultra-smart, helpful personal AI assistant for Omarchy Linux (Arch Linux with Hyprland). "
            "Respond concisely in 1 to 2 conversational sentences as speech feedback. "
            "If the user asks to run an OS command, include a safe bash 'command'. "
            "Return strictly valid JSON with keys: 'command' (string) and 'spoken_response' (string)."
        )

        if (provider == "groq" or provider == "auto") and groq_key:
            try:
                payload = {
                    "model": "llama-3.3-70b-versatile",
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
                        "intent": "max_ai",
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
                    "intent": "max_ollama",
                    "command": parsed.get("command", ""),
                    "spoken_response": parsed.get("spoken_response", "Done."),
                    "category": "ai"
                }
        except Exception:
            pass

        return {
            "status": "matched",
            "intent": "conversational",
            "command": "",
            "spoken_response": f"I heard '{prompt}'. I am Max, and I am here to help you.",
            "category": "conversational"
        }
