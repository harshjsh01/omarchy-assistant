"""
Intent Parser and Command Router for Omarchy Voice Assistant (Bro).
Routes natural language and compound desktop commands directly to the
Antigravity CLI Agent (Gemini) for autonomous execution, maintaining a
single persistent session in ~/Work across all commands and chats.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


class CommandRouter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def route(self, text: str) -> Dict[str, Any]:
        """
        Parse spoken text and return an action dictionary.
        Guarantees prompt and raw_text are populated for ActionExecutor verification.
        """
        clean_text = text.lower().strip()
        if not clean_text or len(clean_text) < 2:
            return {
                "status": "unknown",
                "intent": "empty",
                "command": "",
                "spoken_response": "",
                "prompt": text,
                "raw_text": text,
                "category": "none"
            }

        # Normalize text by stripping punctuation for exact phrase/greeting matching (preserving Devanagari)
        norm_text = re.sub(r"[^\w\s\u0900-\u097f]", " ", clean_text).strip()
        norm_text = re.sub(r"\s+", " ", norm_text)

        # Strip leading wake words before checking intents
        stripped_prompt = re.sub(
            r"^(bro|ब्रो|भाई|hey\s+bro|ok\s+bro|hello\s+bro|hi\s+bro|yo\s+bro|suno\s+bro|हे\s*ब्रो|सुनो\s*ब्रो|नमस्ते\s*ब्रो|सुनो\s*भाई|max|मैक्स|hey\s+max|ok\s+max|hello\s+max|hi\s+max|arrey\s+max|suno\s+max|hey\s+marks|hey\s+macs|kmax|k\s+max|he\s+makes|hay\s+max|हे\s*मैक्स|सुनो\s*मैक्स|नमस्ते\s*मैक्स|अरे\s*मैक्स|ओके\s*मैक्स)[,\s]+",
            "",
            clean_text,
            flags=re.IGNORECASE
        ).strip()
        if not stripped_prompt:
            stripped_prompt = clean_text

        res = self._route_internal(text, clean_text, norm_text, stripped_prompt)
        if isinstance(res, dict):
            res.setdefault("prompt", stripped_prompt)
            res.setdefault("raw_text", text)
        return res

    def _route_internal(self, text: str, clean_text: str, norm_text: str, stripped_prompt: str) -> Dict[str, Any]:
        # 1. Explicit Session Management (ONLY switch sessions when user explicitly requests it)
        if re.search(r"\b(start\s+(a\s+)?(new|fresh)\s+chat|new\s+chat|fresh\s+chat|naya\s+chat|nayi\s+chat|reset\s+(chat|conversation)|clear\s+(chat|conversation)|new\s+conversation|create\s+(a\s+)?new\s+chat|start\s+(a\s+)?new\s+conversation)\b", norm_text):
            new_id = self._create_new_antigravity_session()
            return {
                "status": "matched",
                "intent": "new_chat",
                "command": "",
                "spoken_response": "Starting a fresh Antigravity session.",
                "category": "assistant"
            }

        # 2. Fast direct liveness / greeting checks (instant zero-latency response)
        if re.search(r"^(bro|ब्रो|भाई|hey\s+bro|ok\s+bro|hello\s+bro|hi\s+bro|yo\s+bro|suno\s+bro|हे\s*ब्रो|सुनो\s*ब्रो|नमस्ते\s*ब्रो|सुनो\s*भाई|max|मैक्स|hey\s+max|ok\s+max|hello\s+max|hi\s+max|suno\s+max|marks|macs|kmax|he\s+makes|हे\s*मैक्स|सुनो\s*मैक्स)$", norm_text):
            return {
                "status": "matched",
                "intent": "greeting",
                "command": "",
                "spoken_response": "Yes bro, I am listening.",
                "category": "conversational"
            }

        if re.search(r"^(are\s+you\s+alive|are\s+you\s+there|can\s+you\s+hear\s+me|you\s+alive|zinda\s+ho|sun\s+rahe\s+ho|क्या\s*तुम\s*सुन\s*रहे\s*हो|सुन\s*रहे\s*हो|क्या\s*तुम\s*ज़िंदा\s*हो|ज़िंदा\s*हो)$", norm_text) or re.search(r"^(are\s+you\s+alive|are\s+you\s+there|can\s+you\s+hear\s+me|you\s+alive|zinda\s+ho|sun\s+rahe\s+ho)$", stripped_prompt):
            return {
                "status": "matched",
                "intent": "liveness_check",
                "command": "",
                "spoken_response": "Yes bro, I am live and listening! What is up?",
                "category": "conversational"
            }

        # 3. Continuous Listening / Sleep controls (instant response)
        if re.search(r"^(stop listening|stop continuous listening|stop continuous|go to sleep|chup ho jao|sleep now|chup raho|exit continuous)$|^(सुनना\s*बंद\s*करो|शांत\s*हो\s*जाओ|चुप\s*हो\s*जाओ|सो\s*जाओ|रुक\s*जाओ)$", norm_text) or re.search(r"^(stop listening|stop continuous|go to sleep|chup ho jao|sleep now|chup raho)$", stripped_prompt):
            return {
                "status": "matched",
                "intent": "stop_continuous",
                "command": "omarchy-assistant continuous stop",
                "spoken_response": "Going to sleep. Say Bro whenever you need me.",
                "category": "assistant"
            }

        # 4. Open Live CLI Chat
        if re.search(r"\b(open chat|show chat|view chat|cli chat|chat kholo|open cli chat)\b|(चैट\s*खोलो|चैट\s*दिखाओ|बातचीत\s*दिखाओ)", norm_text):
            return {
                "status": "matched",
                "intent": "open_chat",
                "command": "omarchy launch terminal -e omarchy-assistant chat --cli",
                "spoken_response": "Opening live assistant chat in terminal.",
                "category": "apps"
            }

        # 5. Meeting Controls (daemon internal state)
        if re.search(r"\b(start meeting transcription|start meeting record|record meeting|transcribe meeting|join meeting|meeting record karo|meeting shuru karo|meeting start karo)\b", norm_text):
            return {
                "status": "matched",
                "intent": "start_meeting_transcription",
                "command": "omarchy-assistant meeting start",
                "spoken_response": "Meeting transcription started. Recording your microphone and speaker call audio.",
                "category": "meeting"
            }
        if re.search(r"\b(stop meeting transcription|stop meeting|end meeting|finish meeting|save meeting|meeting band karo|meeting khatam karo|meeting roko)\b", norm_text):
            return {
                "status": "matched",
                "intent": "stop_meeting_transcription",
                "command": "omarchy-assistant meeting stop",
                "spoken_response": "Meeting ended. Saving dual-channel transcript to Documents.",
                "category": "meeting"
            }
        if re.search(r"\b(meeting status|is meeting recording)\b", norm_text):
            return {
                "status": "matched",
                "intent": "meeting_status",
                "command": "omarchy-assistant meeting status",
                "spoken_response": "Checking meeting status.",
                "category": "meeting"
            }

        # 6. DIRECT DELEGATION TO ANTIGRAVITY CLI AGENT FOR ALL COMMANDS & COMPOUND ACTIONS
        return self._run_antigravity_agent(stripped_prompt, raw_text=text)

    def _run_antigravity_agent(self, prompt: str, raw_text: str = "") -> Dict[str, Any]:
        """Execute user prompt directly via the single persistent Antigravity CLI session in ~/Work."""
        try:
            work_dir = os.path.expanduser("~/Work")
            os.makedirs(work_dir, exist_ok=True)
            agy_bin = shutil.which("agy") or os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")
            if not agy_bin or not os.path.exists(agy_bin):
                return self._offline_fallback(prompt, raw_text=raw_text)

            active_conv = self._get_active_conversation_id()
            if not active_conv:
                active_conv = self._create_new_antigravity_session()

            effort = self.config.get("reasoning_effort", "low")
            cmd = [
                agy_bin,
                "--conversation", active_conv,
                "--effort", effort,
                "--dangerously-skip-permissions",
                "--output-format", "json",
                "--print", prompt
            ]

            print(f"[omarchy-assistant] Delegating to Antigravity Agent (conv: {active_conv}): '{prompt}'", flush=True)

            res = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True
            )

            if res.returncode == 0 and res.stdout.strip():
                ans = ""
                try:
                    data = json.loads(res.stdout.strip())
                    ans = data.get("response", "").strip()
                except Exception:
                    ans = res.stdout.strip()

                if ans.startswith("Output:"):
                    ans = ans[7:].strip()

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
                    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_voice) if s.strip()]
                    if len(sentences) > 2:
                        spoken_text = " ".join(sentences[:2])
                    else:
                        spoken_text = clean_voice

                spoken_text = spoken_text.replace("\n", " ").strip()
                if not spoken_text:
                    spoken_text = "Done."

                # Real-time chat logging to ~/Work/CHAT.md for live CLI viewing
                self._log_chat(prompt, ans, spoken_text)

                return {
                    "status": "matched",
                    "intent": "bro_antigravity_agent",
                    "command": "",
                    "spoken_response": spoken_text,
                    "agent_answer": ans,
                    "prompt": prompt,
                    "raw_text": raw_text or prompt,
                    "category": "ai"
                }
            else:
                err_msg = res.stderr.strip() if res.stderr else f"Exit code {res.returncode}"
                print(f"[omarchy-assistant] Antigravity execution error: {err_msg}", file=sys.stderr)
                # Keep active_conv unchanged - never spawn unwanted sessions on errors
                return self._offline_fallback(prompt, raw_text=raw_text)

        except subprocess.TimeoutExpired:
            print("[omarchy-assistant] Antigravity CLI timed out.", file=sys.stderr)
            return {
                "status": "error",
                "intent": "agent_timeout",
                "command": "",
                "spoken_response": "Antigravity took too long to complete. Please try again.",
                "prompt": prompt,
                "raw_text": raw_text or prompt,
                "category": "ai"
            }
        except Exception as e:
            print(f"[omarchy-assistant] Agent execution error: {e}", file=sys.stderr)
            return self._offline_fallback(prompt, raw_text=raw_text)

    def _fallback_llm(self, prompt: str) -> Dict[str, Any]:
        """Alias for _run_antigravity_agent (for compatibility with meeting_transcriber)."""
        return self._run_antigravity_agent(prompt)

    def _offline_fallback(self, prompt: str, raw_text: str = "") -> Dict[str, Any]:
        """Offline fallback if Antigravity CLI is unreachable or errors."""
        clean = prompt.lower().strip()
        actual_raw = raw_text or prompt
        if re.search(r"\b(what time is it|time kya hai|kya time hua hai|current time)\b", clean):
            import datetime
            now_str = datetime.datetime.now().strftime("%I:%M %p")
            return {
                "status": "llm",
                "intent": "current_time",
                "command": "",
                "spoken_response": f"It is currently {now_str}.",
                "prompt": prompt,
                "raw_text": actual_raw,
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
                "prompt": prompt,
                "raw_text": actual_raw,
                "category": "ai"
            }
        if re.search(r"\b(who are you|tum kaun ho|what is your name|apna naam batao)\b", clean):
            return {
                "status": "llm",
                "intent": "persona_identity",
                "command": "",
                "spoken_response": "I am Bro, your autonomous conversational desktop AI assistant for Omarchy Linux.",
                "prompt": prompt,
                "raw_text": actual_raw,
                "category": "ai"
            }
        return {
            "status": "error",
            "intent": "agent_error",
            "command": "",
            "spoken_response": "I encountered an error executing that command. Please try again.",
            "prompt": prompt,
            "raw_text": actual_raw,
            "category": "ai"
        }

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

        # If not on disk, check conversation_summaries.db for existing session in ~/Work
        try:
            import sqlite3
            db_path = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
            if os.path.exists(db_path):
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    row = cur.execute(
                        "SELECT conversation_id FROM conversation_summaries "
                        "WHERE workspace_uris LIKE '%Work%' "
                        "AND conversation_id NOT IN ('42be53a5-6dfe-4730-b1b5-42d8d1159d6f') "
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

        # Only if still none found, create one now and lock it in
        return self._create_new_antigravity_session()

    def _create_new_antigravity_session(self) -> str:
        """Start a fresh conversation in ~/Work and return its conversation ID."""
        try:
            work_dir = os.path.expanduser("~/Work")
            os.makedirs(work_dir, exist_ok=True)
            agy_bin = shutil.which("agy") or os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")
            if not agy_bin or not os.path.exists(agy_bin):
                return ""
            res = subprocess.run(
                [agy_bin, "--effort", "low", "--dangerously-skip-permissions", "--output-format", "json", "--print", "Hello Bro, fresh session initialized."],
                cwd=work_dir,
                capture_output=True,
                text=True
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
