"""
Intent Parser and Command Router.
Maps spoken natural language phrases to Omarchy Linux actions.
Includes fast regex rules and optional LLM fallback.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
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
        if not clean_text or len(clean_text) < 2:
            return {
                "status": "unknown",
                "intent": "empty",
                "command": "",
                "spoken_response": "",
                "category": "none"
            }

        # Normalize text by stripping punctuation for exact phrase/greeting matching (preserving Devanagari)
        norm_text = re.sub(r"[^\w\s\u0900-\u097f]", " ", clean_text).strip()
        norm_text = re.sub(r"\s+", " ", norm_text)

        # 1. Internal Daemon Controls
        if re.search(r"\b(start new chat|new conversation|naya chat|reset chat|clear chat)\b", norm_text):
            new_id = self._create_new_antigravity_session()
            return {
                "status": "matched",
                "intent": "new_chat",
                "command": "",
                "spoken_response": "Starting a fresh Antigravity session.",
                "category": "ai"
            }

        # 2. Fast direct liveness / greeting checks (instant response when user simply calls "Bro" or "Max")
        if re.search(r"^(bro|ब्रो|भाई|hey\s+bro|ok\s+bro|hello\s+bro|hi\s+bro|yo\s+bro|suno\s+bro|हे\s*ब्रो|सुनो\s*ब्रो|नमस्ते\s*ब्रो|सुनो\s*भाई|max|मैक्स|hey\s+max|ok\s+max|hello\s+max|hi\s+max|suno\s+max|marks|macs|kmax|he\s+makes|हे\s*मैक्स|सुनो\s*मैक्स)$", norm_text):
            spoken = "हाँ भाई, बोलो?" if re.search(r"[\u0900-\u097f]", norm_text) else "Yes bro, I'm listening."
            return {
                "status": "matched",
                "intent": "greeting",
                "command": "",
                "spoken_response": spoken,
                "category": "conversational"
            }

        if re.search(r"^(are\s+you\s+alive|are\s+you\s+there|can\s+you\s+hear\s+me|you\s+alive|zinda\s+ho|sun\s+rahe\s+ho|क्या\s*तुम\s*सुन\s*रहे\s*हो|सुन\s*रहे\s*हो|क्या\s*तुम\s*ज़िंदा\s*हो|ज़िंदा\s*हो)$", norm_text):
            spoken = "हाँ भाई, मैं बिल्कुल लाइव और तैयार हूँ। बोलो क्या काम है?" if re.search(r"[\u0900-\u097f]", norm_text) else "Yes bro, I am live and listening! What's up?"
            return {
                "status": "matched",
                "intent": "liveness_check",
                "command": "",
                "spoken_response": spoken,
                "category": "conversational"
            }

        # Strip leading wake words (English, Hinglish, Devanagari)
        stripped_prompt = re.sub(
            r"^(bro|ब्रो|भाई|hey\s+bro|ok\s+bro|hello\s+bro|hi\s+bro|yo\s+bro|suno\s+bro|हे\s*ब्रो|सुनो\s*ब्रो|नमस्ते\s*ब्रो|सुनो\s*भाई|max|मैक्स|hey\s+max|ok\s+max|hello\s+max|hi\s+max|arrey\s+max|suno\s+max|hey\s+marks|hey\s+macs|kmax|k\s+max|he\s+makes|hay\s+max|हे\s*मैक्स|सुनो\s*मैक्स|नमस्ते\s*मैक्स|अरे\s*मैक्स|ओके\s*मैक्स)[,\s]+",
            "",
            clean_text,
            flags=re.IGNORECASE
        ).strip()
        if not stripped_prompt:
            stripped_prompt = clean_text

        # 3. Instant local hardware & media rules (10ms execution for volume, brightness, media, workspaces, monitoring)
        hardware_match = self._match_rules(stripped_prompt)
        if hardware_match and hardware_match.get("category") in ["audio", "media", "display", "hyprland", "apps", "system"]:
            self._log_chat(text, f"Executed: `{hardware_match.get('command')}`", hardware_match.get("spoken_response", ""))
            return hardware_match

        # 4. DIRECT ANTIGRAVITY AUTONOMOUS ENGINE FOR EVERYTHING ELSE!
        # Send stripped prompt directly to the active Antigravity CLI session without alteration
        llm_result = self._fallback_llm(stripped_prompt)
        if llm_result:
            return llm_result

        # 5. Fallback to matched rules if Antigravity is offline
        if hardware_match:
            return hardware_match

        return {
            "status": "unknown",
            "intent": "unknown",
            "command": "",
            "spoken_response": f"I heard '{text}'.",
            "category": "none"
        }

    def _match_rules(self, text: str) -> Optional[Dict[str, Any]]:
        # --- Audio & Volume (English + Hindi/Hinglish) ---
        # --- Audio & Volume (English + Hindi/Hinglish + Devanagari) ---
        if re.search(r"\b(volume up|increase volume|louder|sound up|aa?wa?a?[zj] badhao|volume badhao|aa?wa?a?[zj] badha do|aawaz badhao)\b|(वॉल्यूम\s*बढ़ाओ|आवाज़\s*बढ़ाओ|आवाज़\s*तेज़\s*करो|साउंड\s*बढ़ाओ)", text, re.IGNORECASE):
            spoken = "वॉल्यूम बढ़ा दिया है।" if re.search(r"[\u0900-\u097f]", text) else "Volume up"
            return {
                "status": "matched",
                "intent": "volume_up",
                "command": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
                "spoken_response": spoken,
                "category": "audio"
            }
        if re.search(r"\b(volume down|decrease volume|softer|sound down|lower volume|aa?wa?a?[zj] kam karo|volume kam karo|aa?wa?a?[zj] dheemi karo|aawaz kam karo)\b|(वॉल्यूम\s*कम\s*करो|आवाज़\s*कम\s*करो|आवाज़\s*धीमी\s*करो|साउंड\s*कम\s*करो)", text, re.IGNORECASE):
            spoken = "वॉल्यूम कम कर दिया है।" if re.search(r"[\u0900-\u097f]", text) else "Volume down"
            return {
                "status": "matched",
                "intent": "volume_down",
                "command": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
                "spoken_response": spoken,
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
        if re.search(r"\b(mute microphone|mute mic|mic band karo|mike band karo|mic mute karo)\b|(माइक\s*बंद\s*करो|माइक\s*म्यूट\s*करो)", text, re.IGNORECASE):
            return {
                "status": "matched",
                "intent": "mute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1",
                "spoken_response": "Microphone muted",
                "category": "audio"
            }
        if re.search(r"\b(unmute microphone|unmute mic|mic chalu karo|mic on karo|unmute mic karo)\b|(माइक\s*चालू\s*करो|माइक\s*ऑन\s*करो)", text, re.IGNORECASE):
            return {
                "status": "matched",
                "intent": "unmute_mic",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0",
                "spoken_response": "Microphone unmuted",
                "category": "audio"
            }
        if re.search(r"\b(mute audio|mute sound|mute|unmute|aa?wa?a?[zj] band karo|chup karo)\b|(वॉल्यूम\s*बंद\s*करो|आवाज़\s*बंद\s*करो|म्यूट\s*करो)", text, re.IGNORECASE):
            spoken = "म्यूट टॉगल कर दिया है।" if re.search(r"[\u0900-\u097f]", text) else "Toggled mute"
            return {
                "status": "matched",
                "intent": "toggle_mute",
                "command": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
                "spoken_response": spoken,
                "category": "audio"
            }

        # --- Live CLI Chat Command ---
        if re.search(r"\b(open chat|show chat|view chat|cli chat|chat kholo|open cli chat)\b|(चैट\s*खोलो|चैट\s*दिखाओ|बातचीत\s*दिखाओ)", text, re.IGNORECASE):
            return {
                "status": "matched",
                "intent": "open_chat",
                "command": "omarchy launch terminal -e omarchy-assistant chat",
                "spoken_response": "Opening live assistant chat in terminal.",
                "category": "apps"
            }

        # --- Terminal & Browser Launches ---
        if re.search(r"\b(open terminal|terminal kholo|launch terminal)\b|(टर्मिनल\s*खोलो|टर्मिनल\s*चलाओ|टर्मिनल\s*ऑन\s*करो)", text, re.IGNORECASE):
            spoken = "टर्मिनल खोल रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else "Opening terminal"
            return {
                "status": "matched",
                "intent": "open_terminal",
                "command": "omarchy launch terminal",
                "spoken_response": spoken,
                "category": "apps"
            }
        if re.search(r"\b(open browser|browser kholo|launch browser)\b|(ब्राउज़र\s*खोलो|ब्राउज़र\s*चलाओ)", text, re.IGNORECASE):
            spoken = "ब्राउज़र खोल रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else "Opening browser"
            return {
                "status": "matched",
                "intent": "open_browser",
                "command": "omarchy launch browser",
                "spoken_response": spoken,
                "category": "apps"
            }

        # --- Specific Media Destination (YouTube, Spotify, Web) ---
        # 1. YouTube playback and search (English, Hinglish, Devanagari Hindi)
        m_yt = re.search(r"\b(?:play|search for|search|listen to)\s+(?:a\s+|the\s+)?(?:song|track|music|video)?\s*(?:called|named)?\s*(.*?)\s*(?:on|in|from)\s*(?:youtube|yt)\b", text, re.IGNORECASE)
        if not m_yt:
            m_yt = re.search(r"\b(?:on|in)\s+(?:youtube|yt)\s+(?:play|search for|search|listen to)\s+(.*)\b", text, re.IGNORECASE)
        if not m_yt:
            m_yt = re.search(r"\byoutube\s+(?:par|pe)\s+(.*?)\s*(?:chalao|bajao|kholo|play karo)\b", text, re.IGNORECASE)
        if not m_yt:
            m_yt = re.search(r"(?:यूट्यूब|yt)\s*(?:पर|पे)?\s*(.*?)\s*(?:चलाओ|खोलो|बजाओ|लगाओ|प्ले\s*करो|सर्च\s*करो)", text, re.IGNORECASE)
        if not m_yt:
            m_yt = re.search(r"(?:चलाओ|बजाओ|लगाओ|सुनो)\s*(.*?)\s*(?:यूट्यूब|yt)\s*(?:पर|पे)?", text, re.IGNORECASE)
        if not m_yt:
            m_yt = re.search(r"\b(?:open\s+youtube\s+and\s+play|play\s+on\s+youtube)\s*(.*)\b", text, re.IGNORECASE)

        if m_yt:
            query = m_yt.group(1).strip()
            # Clean up filler words like "song", "track", "music", "please", "some"
            query = re.sub(r"^(?:a\s+|some\s+|any\s+|the\s+)?(?:song|music|track|video)(?:\s+called|\s+named)?\s*", "", query, flags=re.IGNORECASE).strip()
            query = re.sub(r"^(?:गाना|गीत|वीडियो|म्यूजिक)\s*", "", query, flags=re.IGNORECASE).strip()
            query = re.sub(r"^(?:please|kindly|jarur|कृपया)\s*", "", query, flags=re.IGNORECASE).strip()
            import urllib.parse
            if query:
                encoded = urllib.parse.quote_plus(query)
                spoken = f"यूट्यूब पर {query} चला रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else f"Playing {query} on YouTube"
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": f"omarchy launch browser 'https://www.youtube.com/results?search_query={encoded}'",
                    "spoken_response": spoken,
                    "category": "apps"
                }
            else:
                spoken = "यूट्यूब खोल रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else "Opening YouTube"
                return {
                    "status": "matched",
                    "intent": "open_youtube",
                    "command": "omarchy launch browser 'https://youtube.com'",
                    "spoken_response": spoken,
                    "category": "apps"
                }

        if re.search(r"\b(open youtube|youtube kholo|play youtube|launch youtube)\b|(यूट्यूब\s*खोलो|यूट्यूब\s*चलाओ|ओपन\s*यूट्यूब)", text, re.IGNORECASE):
            spoken = "यूट्यूब खोल रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else "Opening YouTube"
            return {
                "status": "matched",
                "intent": "open_youtube",
                "command": "omarchy launch browser 'https://youtube.com'",
                "spoken_response": spoken,
                "category": "apps"
            }

        # 2. Spotify playback
        m_sp = re.search(r"\b(?:play|listen to)\s+(?:a\s+|the\s+)?(?:song|track|music)?\s*(?:called|named)?\s*(.*?)\s*(?:on|in)\s*spotify\b", text, re.IGNORECASE)
        if not m_sp:
            m_sp = re.search(r"\bspotify\s+(?:par|pe)\s+(.*?)\s*(?:chalao|bajao|kholo|play karo)\b", text, re.IGNORECASE)
        if not m_sp:
            m_sp = re.search(r"स्पॉटिफ़ाई\s*(?:पर|पे)?\s*(.*?)\s*(?:चलाओ|बजाओ|खोलो)", text, re.IGNORECASE)
        if m_sp:
            query = m_sp.group(1).strip()
            query = re.sub(r"^(?:a\s+|some\s+|the\s+)?(?:song|music|track)(?:\s+called|\s+named)?\s*", "", query, flags=re.IGNORECASE).strip()
            import urllib.parse
            if query:
                encoded = urllib.parse.quote_plus(query)
                return {
                    "status": "matched",
                    "intent": "play_spotify",
                    "command": f"omarchy launch browser 'https://open.spotify.com/search/{encoded}'",
                    "spoken_response": f"Searching for {query} on Spotify",
                    "category": "apps"
                }
            else:
                return {
                    "status": "matched",
                    "intent": "open_spotify",
                    "command": "omarchy launch spotify || omarchy launch browser 'https://open.spotify.com'",
                    "spoken_response": "Opening Spotify",
                    "category": "apps"
                }

        # 3. Direct song playback request in English or Hindi Devanagari
        m_dev_song = re.search(r"(.*?)\s*(?:का\s*गाना|गाना|गीत)\s*(?:चलाओ|बजाओ|लगाओ|सुनाओ)", text)
        if not m_dev_song:
            m_dev_song = re.search(r"(?:गाना|गीत)\s*(?:चलाओ|बजाओ|लगाओ|सुनाओ)\s*(.*)", text)
        if m_dev_song:
            target = m_dev_song.group(1).strip()
            target = re.sub(r"^(?:कोई\s*अच्छा|कोई|एक)\s*", "", target).strip()
            import urllib.parse
            if target and target not in ["चलाओ", "बजाओ", "लगाओ", "सुनाओ", ""]:
                encoded = urllib.parse.quote_plus(target + " song")
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": f"omarchy launch browser 'https://www.youtube.com/results?search_query={encoded}'",
                    "spoken_response": f"यूट्यूब पर {target} का गाना चला रहा हूँ।",
                    "category": "apps"
                }
            else:
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": "omarchy launch browser 'https://www.youtube.com/results?search_query=top+hindi+songs'",
                    "spoken_response": "यूट्यूब पर गाने चला रहा हूँ।",
                    "category": "apps"
                }

        m_song = re.search(r"^(?:play|listen to)\s+(?:song\s+|music\s+|track\s+)?([a-zA-Z0-9\s]+)$", text, re.IGNORECASE)
        if m_song:
            target = m_song.group(1).strip()
            # Ignore generic words that just mean play/resume
            if target.lower() not in ["music", "track", "song", "audio", "video", "something"]:
                import urllib.parse
                encoded = urllib.parse.quote_plus(target)
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": f"omarchy launch browser 'https://www.youtube.com/results?search_query={encoded}'",
                    "spoken_response": f"Playing {target} on YouTube",
                    "category": "apps"
                }

        m_hinglish_song = re.search(r"^(.*?)\s+(?:ka\s+gaana\s+)?(?:bajao|chalao|play karo)$", text, re.IGNORECASE)
        if m_hinglish_song:
            target = m_hinglish_song.group(1).strip()
            target = re.sub(r"^(?:koi\s+achha|koi|ek)\s*", "", target, flags=re.IGNORECASE).strip()
            if target.lower() in ["kuch", "kuchh", "koi gaana", "koi gana", "koi song", "achha gaana", "achha gana"]:
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": "omarchy launch browser 'https://www.youtube.com/results?search_query=top+hindi+songs'",
                    "spoken_response": "Playing popular songs on YouTube",
                    "category": "apps"
                }
            if target.lower() not in ["gaana", "gana", "music", "song", "audio", ""]:
                import urllib.parse
                encoded = urllib.parse.quote_plus(target + " song")
                spoken = f"यूट्यूब पर {target} चला रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else f"Playing {target} on YouTube"
                return {
                    "status": "matched",
                    "intent": "play_youtube",
                    "command": f"omarchy launch browser 'https://www.youtube.com/results?search_query={encoded}'",
                    "spoken_response": spoken,
                    "category": "apps"
                }

        # --- Media Playback Controls (ONLY for toggling currently playing audio) ---
        if re.search(r"^(pause|pause music|pause video|pause playback|stop playback|gaana roko|gana roko|roko|गाना\s*रोको|रोको|पॉज़\s*करो|बंद\s*करो)$", text):
            spoken = "पॉज़ कर दिया है।" if re.search(r"[\u0900-\u097f]", text) else "Paused"
            return {
                "status": "matched",
                "intent": "media_pause",
                "command": "playerctl pause 2>/dev/null || true",
                "spoken_response": spoken,
                "category": "media"
            }
        if re.search(r"^(play|resume|play music|resume music|play track|resume track|continue playback|gaana bajao|gana bajao|gaana chalao|gana chalao|गाना\s*चलाओ|चलाओ|बजाओ|रिज्यूम\s*करो)$", text):
            spoken = "प्ले कर रहा हूँ।" if re.search(r"[\u0900-\u097f]", text) else "Playing"
            return {
                "status": "matched",
                "intent": "media_play",
                "command": "playerctl play-pause 2>/dev/null || true",
                "spoken_response": spoken,
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
        if re.search(r"\b(open btop|system monitor|task manager|monitor kholo|monitor\s+(a\s+)?activity|system\s+activity|activity\s+monitor|check\s+activity)\b", text):
            return {
                "status": "matched",
                "intent": "launch_btop",
                "command": "omarchy launch terminal -e btop &",
                "spoken_response": "Opening system activity monitor",
                "category": "apps"
            }
        # --- Antigravity AI Agent (English + Hindi/Hinglish + phonetic mishearing tolerance) ---
        if re.search(r"\b(launch|open|start|run)?\s*(antigravity|anti\s*gravity|agy|integrity)\b", text) or \
           re.search(r"\b(antigravity|anti\s*gravity|agy|integrity)\s*(kholo|chalao|start karo|open karo)?\b", text):
            return {
                "status": "matched",
                "intent": "launch_antigravity",
                "command": "omarchy launch or focus tui --app-id=org.omarchy.agent agy",
                "spoken_response": "Launching Antigravity AI Agent",
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

        # --- Generic Application Launching (open <app> / launch <app> / <app> kholo) ---
        m = re.search(r"^(open|launch|start)\s+([a-zA-Z0-9_\-\.\+]+)$", text)
        if not m:
            m = re.search(r"^([a-zA-Z0-9_\-\.\+]+)\s+(kholo|chalao|open karo|launch karo)$", text)
        if m:
            target_app = m.group(2) if m.group(1) in ["open", "launch", "start"] else m.group(1)
            target_lower = target_app.lower()
            if target_lower not in ["the", "a", "an", "window", "terminal", "browser", "chat", "menu", "sound", "volume", "music", "integrity", "antigravity"]:
                clean_target = target_app.replace("'", "").replace("\"", "")
                return {
                    "status": "matched",
                    "intent": "launch_generic_app",
                    "command": f"bash -c 'omarchy launch or focus \"{clean_target}\" \"{clean_target}\" 2>/dev/null || gtk-launch {clean_target} 2>/dev/null || {clean_target} &'",
                    "spoken_response": f"Opening {target_app}",
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
                "spoken_response": "Going to sleep. Say Bro whenever you need me.",
                "category": "assistant"
            }
        # --- Chat Session Management ---
        if re.search(r"\b(start\s+(a\s+)?(new|fresh)\s+chat|new\s+chat|fresh\s+chat|naya\s+chat|nayi\s+chat|reset\s+(chat|conversation)|clear\s+(chat|conversation)|new\s+conversation|create\s+(a\s+)?new\s+chat|start\s+(a\s+)?new\s+conversation)\b", text):
            new_id = self._create_new_antigravity_session()
            return {
                "status": "matched",
                "intent": "new_chat",
                "command": "",
                "spoken_response": "Started a new chat session for you. What would you like to discuss?",
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

    def _create_new_antigravity_session(self) -> str:
        """Start a fresh conversation in ~/Work/chat and return its conversation ID."""
        try:
            chat_dir = os.path.expanduser("~/Work/chat")
            os.makedirs(chat_dir, exist_ok=True)
            agy_bin = shutil.which("agy") or os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")
            if not agy_bin or not os.path.exists(agy_bin):
                return ""
            res = subprocess.run(
                [agy_bin, "--effort", "low", "--output-format", "json", "--print", "You are Bro. I will call you Bro."],
                cwd=chat_dir,
                capture_output=True,
                text=True,
                timeout=35
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                new_id = data.get("conversation_id", "")
                if new_id:
                    conv_file = os.path.expanduser("~/.config/omarchy-assistant/active_conversation_id.txt")
                    os.makedirs(os.path.dirname(conv_file), exist_ok=True)
                    with open(conv_file, "w") as f:
                        f.write(new_id)
                    return new_id
        except Exception as e:
            print(f"[omarchy-assistant] Failed to start new Antigravity session: {e}", file=sys.stderr)
        return ""

    def _get_active_conversation_id(self) -> str:
        """Retrieve the active conversation ID, ensuring we NEVER spawn accidental new chats."""
        conv_file = os.path.expanduser("~/.config/omarchy-assistant/active_conversation_id.txt")
        if os.path.exists(conv_file):
            try:
                with open(conv_file, "r") as f:
                    cid = f.read().strip()
                    if cid:
                        return cid
            except Exception:
                pass

        # If not on disk, check conversation_summaries.db for existing chat in ~/Work/chat or ~/Work
        try:
            import sqlite3
            db_path = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
            if os.path.exists(db_path):
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    row = cur.execute(
                        "SELECT conversation_id FROM conversation_summaries "
                        "WHERE workspace_uris LIKE '%Work%' "
                        "ORDER BY last_modified_time DESC LIMIT 1"
                    ).fetchone()
                    if row and row[0]:
                        cid = row[0]
                        os.makedirs(os.path.dirname(conv_file), exist_ok=True)
                        with open(conv_file, "w") as f:
                            f.write(cid)
                        return cid
        except Exception:
            pass

        # If still none found, create one now and lock it in
        return self._create_new_antigravity_session()

    def _fallback_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Conversational AI engine for Max (live Antigravity Gemini session + offline fallback)."""
        clean = prompt.lower().strip()

        # 1. Primary Intelligence: Antigravity CLI (Gemini 3.8 Flash via active Google AI Pro session in ~/Work/chat)
        try:
            chat_dir = os.path.expanduser("~/Work/chat")
            os.makedirs(chat_dir, exist_ok=True)
            agy_bin = shutil.which("agy") or os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")
            if agy_bin and os.path.exists(agy_bin):
                active_conv = self._get_active_conversation_id()

                # Dynamic reasoning effort based on task complexity (brainstorming, coding, planning)
                is_complex = bool(re.search(r"\b(brainstorm|project|idea|plan|documentation|docs|build|create\s+folder|architecture|code|develop|create|system|design)\b", clean))
                effort = "high" if is_complex else self.config.get("reasoning_effort", "low")

                # Auto-approve tool permissions so Max can autonomously create folders, docs, and run commands
                cmd = [
                    agy_bin,
                    "--effort", effort,
                    "--dangerously-skip-permissions",
                    "--output-format", "json",
                    "--print", prompt
                ]
                if active_conv:
                    cmd.insert(1, "--conversation")
                    cmd.insert(2, active_conv)

                timeout_sec = 120 if is_complex else 60
                res = subprocess.run(
                    cmd,
                    cwd=chat_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec
                )
                if res.returncode != 0 and active_conv:
                    # In case active conversation is corrupted or invalid, auto-retry with fresh session
                    cmd_fresh = [
                        agy_bin,
                        "--effort", effort,
                        "--dangerously-skip-permissions",
                        "--output-format", "json",
                        "--print", prompt
                    ]
                    res = subprocess.run(
                        cmd_fresh,
                        cwd=chat_dir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec
                    )
                if res.returncode == 0 and res.stdout.strip():
                    ans = ""
                    try:
                        data = json.loads(res.stdout.strip())
                        new_conv = data.get("conversation_id", "")
                        if new_conv:
                            conv_file = os.path.expanduser("~/.config/omarchy-assistant/active_conversation_id.txt")
                            with open(conv_file, "w") as f:
                                f.write(new_conv)
                        ans = data.get("response", "").strip()
                    except Exception:
                        ans = res.stdout.strip()

                    if ans.startswith("Output:"):
                        ans = ans[7:].strip()

                    # Save full detailed response/plan to disk
                    try:
                        with open(os.path.join(chat_dir, "last_response.md"), "w", encoding="utf-8") as f_out:
                            f_out.write(ans)
                    except Exception:
                        pass

                    # Extract spoken voice summary if formatted with [Spoken Summary]:
                    spoken_text = ""
                    if "[Spoken Summary]:" in ans:
                        spoken_text = ans.split("[Spoken Summary]:")[-1].strip()
                    elif "[spoken summary]:" in ans.lower():
                        idx = ans.lower().find("[spoken summary]:")
                        spoken_text = ans[idx + len("[spoken summary]:"):].strip()
                    else:
                        # Clean markdown formatting for speech
                        clean_voice = re.sub(r"```.*?```", "", ans, flags=re.DOTALL)
                        clean_voice = re.sub(r"[*#`_\[\]>]", "", clean_voice).strip()
                        # If the answer is long (e.g. documentation or deep brainstorming), speak the overview
                        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_voice) if s.strip()]
                        if len(sentences) > 3:
                            spoken_text = " ".join(sentences[:2]) + " I have detailed the full documentation and files in your workspace."
                        else:
                            spoken_text = clean_voice

                    spoken_text = spoken_text.replace("\n", " ").strip()

                    # Real-time chat logging to ~/Work/CHAT.md for live CLI viewing
                    self._log_chat(prompt, ans, spoken_text)

                    return {
                        "status": "matched",
                        "intent": "max_antigravity_ai",
                        "command": "",
                        "spoken_response": spoken_text,
                        "category": "ai"
                    }
        except Exception as e:
            print(f"[omarchy-assistant] Antigravity chat error: {e}", file=sys.stderr)

        # 2. Offline Fallback: Time and Date
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

        # 3. Offline Fallback: Basic math
        calc_match = re.search(r"(?:what is|calculate|solve)?\s*(\d+(?:\.\d+)?\s*[\+\-\*\/xX]\s*\d+(?:\.\d+)?)\b", clean)
        if calc_match:
            expr = calc_match.group(1).replace("x", "*").replace("X", "*")
            try:
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

        # 4. Offline Fallback: Battery
        if re.search(r"\b(battery|battery level|battery percentage)\b", clean):
            return {
                "status": "llm",
                "intent": "battery_status",
                "command": "upower -i $(upower -e | grep 'BAT') 2>/dev/null | grep -E 'percentage|state' || echo 'No battery found'",
                "spoken_response": "Checking battery status.",
                "category": "system"
            }

        # 5. Offline Fallback: Remember / Memory
        mem_match = re.search(r"\b(?:remember\s+(?:that|this)?|yaad\s+rakhna\s+(?:ki)?)\s+(.+)", clean)
        if mem_match:
            note = mem_match.group(1).strip()
            import datetime
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mem_file = os.path.expanduser("~/Work/MEMORY.md")
            try:
                with open(mem_file, "a", encoding="utf-8") as f:
                    f.write(f"\n- **[{ts}]**: {note}")
                return {
                    "status": "matched",
                    "intent": "memory_store",
                    "command": "",
                    "spoken_response": f"I've remembered that: {note}.",
                    "category": "ai"
                }
            except Exception:
                pass

        # 6. Offline Fallback: Reminders
        rem_match = re.search(r"\bremind\s+me\s+in\s+(\d+)\s*(minute|minutes|min|mins|ghante|ghanta|hour|hours)?\s*(?:to\s+)?(.+)", clean)
        if rem_match:
            val = int(rem_match.group(1))
            unit = rem_match.group(2) or "minutes"
            mins = val * 60 if "hour" in unit or "ghanta" in unit else val
            task = rem_match.group(3).strip()
            import datetime
            created_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            sched_ts = (datetime.datetime.now() + datetime.timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M")
            rem_file = os.path.expanduser("~/Work/REMIND.md")
            try:
                with open(rem_file, "a", encoding="utf-8") as f:
                    f.write(f"\n| {int(datetime.datetime.now().timestamp()) % 10000:04d} | {created_ts} | {sched_ts} | {task} | omarchy reminder {mins} | Active |")
            except Exception:
                pass
            return {
                "status": "matched",
                "intent": "set_reminder",
                "command": f"omarchy reminder {mins} {json.dumps(task)}",
                "spoken_response": f"Reminder set for {mins} minutes from now to {task}.",
                "category": "system"
            }

        # 7. Offline Fallback: Identity & Persona (Bro)
        if re.search(r"\b(who are you|tum kaun ho|what is your name|apna naam batao|tell me about yourself)\b", clean):
            return {
                "status": "llm",
                "intent": "persona_identity",
                "command": "",
                "spoken_response": "I am Bro, your personal voice assistant for Omarchy Linux. I can control your desktop, workspaces, windows, launch apps, record meetings, and answer your questions.",
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
                "spoken_response": "Sab badiya bro! Running at peak performance and ready to assist you!",
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

        # 6. Cloud LLM (Groq / Ollama / OpenAI) if configured
        provider = self.config.get("llm_provider", "auto")
        groq_key = self.config.get("groq_api_key") or os.getenv("GROQ_API_KEY")

        system_instruction = (
            "You are Bro, an ultra-smart, helpful personal AI assistant for Omarchy Linux (Arch Linux with Hyprland). "
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
            "spoken_response": f"I heard '{prompt}'. I am Bro, and I am here to help you.",
            "category": "conversational"
        }

    def _log_chat(self, user_prompt: str, assistant_response: str, spoken: str = ""):
        """Appends conversation turn to ~/Work/chat/CHAT.md and ensures ~/Work/CHAT.md symlink exists."""
        try:
            import datetime
            chat_dir = Path.home() / "Work" / "chat"
            chat_dir.mkdir(parents=True, exist_ok=True)
            chat_file = chat_dir / "CHAT.md"
            symlink_file = Path.home() / "Work" / "CHAT.md"

            if not chat_file.exists():
                chat_file.write_text(
                    "# 💬 Bro Voice Assistant Live Chat Log\n"
                    "*Real-time conversational log between you and Bro (powered by Google Gemini via Antigravity).*\n"
                    "- **CLI Command to View:** `omarchy-assistant chat`\n"
                    "- **Interactive CLI Session:** `omarchy-assistant chat --cli`\n\n"
                    "---\n\n",
                    encoding="utf-8"
                )

            if not symlink_file.exists() and not symlink_file.is_symlink():
                try:
                    symlink_file.symlink_to(chat_file)
                except Exception:
                    pass

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"### 👤 You [{now_str}]\n> {user_prompt}\n\n### 🤖 Bro (Antigravity Gemini)\n{assistant_response}\n\n"
            if spoken:
                entry += f"**Spoken Summary:** *{spoken}*\n\n"
            entry += "---\n\n"

            with open(chat_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            print(f"[omarchy-assistant] Failed to log chat: {e}", file=sys.stderr)

