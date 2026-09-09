"""
Session Manager for Omarchy Voice Assistant (Bro).
Maintains an index of all Antigravity CLI sessions in ~/Work, generates human-readable
summaries in ~/Work/SESSIONS.md, and allows semantic natural-language switching to past
conversations (e.g., "switch to the session where we played Seedhe Maut").
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


META_SESSION_ID = "42be53a5-6dfe-4730-b1b5-42d8d1159d6f"
CANONICAL_MAIN_SESSION = "956ae870-07b0-4a98-ba10-bda0c72f7c81"


class SessionManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.work_dir = Path.home() / "Work"
        self.cfg_dir = Path.home() / ".config" / "omarchy-assistant"
        self.cfg_dir.mkdir(parents=True, exist_ok=True)
        
        self.sessions_json_path = self.cfg_dir / "sessions.json"
        self.sessions_md_path = self.work_dir / "SESSIONS.md"
        self.active_file = self.cfg_dir / "active_conversation_id.txt"
        self.prev_file = self.cfg_dir / "previous_conversation_id.txt"
        self.db_path = Path.home() / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
        self.brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"

    def get_active_session_id(self) -> str:
        """Retrieve active conversation ID from disk, avoiding meta session."""
        if self.active_file.exists():
            try:
                cid = self.active_file.read_text(encoding="utf-8").strip()
                if cid and cid != META_SESSION_ID:
                    return cid
            except Exception:
                pass
        return CANONICAL_MAIN_SESSION

    def set_active_session_id(self, conv_id: str) -> None:
        """Persist active conversation ID and record old one as previous."""
        if not conv_id or conv_id == META_SESSION_ID:
            return
        current = self.get_active_session_id()
        if current and current != conv_id and current != META_SESSION_ID:
            try:
                self.prev_file.write_text(current, encoding="utf-8")
            except Exception:
                pass
        self.active_file.write_text(conv_id, encoding="utf-8")

    def get_previous_session_id(self) -> Optional[str]:
        """Retrieve previous conversation ID."""
        if self.prev_file.exists():
            try:
                cid = self.prev_file.read_text(encoding="utf-8").strip()
                if cid and cid != META_SESSION_ID:
                    return cid
            except Exception:
                pass
        return None

    def sync_sessions(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Scan conversation_summaries.db and transcript logs, build rich summaries,
        and write both ~/.config/omarchy-assistant/sessions.json and ~/Work/SESSIONS.md.
        """
        if not self.db_path.exists():
            return []

        active_cid = self.get_active_session_id()
        sessions: List[Dict[str, Any]] = []

        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT conversation_id, title, preview, step_count, last_modified_time
                    FROM conversation_summaries
                    WHERE workspace_uris LIKE '%Work%'
                    AND conversation_id != ?
                    ORDER BY last_modified_time DESC
                    """,
                    (META_SESSION_ID,)
                ).fetchall()
        except Exception as e:
            print(f"[session_manager] DB error: {e}")
            return []

        for cid, title, prev, step_count, last_mod in rows:
            tpath = self.brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
            prompts: List[str] = []
            if tpath.exists():
                try:
                    with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if '"USER_INPUT"' in line or '"USER_EXPLICIT"' in line:
                                try:
                                    d = json.loads(line)
                                    c = d.get("content", "")
                                    if "<USER_REQUEST>" in c:
                                        c = c.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                                    c_clean = re.sub(r"\s+", " ", c).strip()
                                    if c_clean and c_clean not in prompts and len(c_clean) < 180:
                                        prompts.append(c_clean)
                                except Exception:
                                    pass
                except Exception:
                    pass

            # Auto-derive friendly title if empty or generic
            clean_title = (title or "").strip()
            if not clean_title or clean_title == "Untitled":
                clean_title = self._infer_title(prompts, prev, cid)

            # Generate concise summary of what was done
            summary, tags = self._infer_summary_and_tags(clean_title, prompts, prev)

            # Format datetime
            dt_str = str(last_mod)
            try:
                dt_clean = dt_str.split(".")[0]
                dt = datetime.strptime(dt_clean, "%Y-%m-%d %H:%M:%S")
                date_display = dt.strftime("%Y-%m-%d %I:%M %p")
            except Exception:
                date_display = dt_str[:16]

            sessions.append({
                "id": cid,
                "short_id": cid[:8],
                "title": clean_title,
                "preview": prev[:140] if prev else "",
                "step_count": step_count,
                "last_modified": dt_str,
                "date_display": date_display,
                "prompts_sample": prompts[:5],
                "summary": summary,
                "tags": tags,
                "is_active": (cid == active_cid)
            })

        # Save to JSON
        try:
            with open(self.sessions_json_path, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2)
        except Exception as e:
            print(f"[session_manager] JSON write error: {e}")

        # Render to ~/Work/SESSIONS.md
        self._render_markdown(sessions, active_cid)
        return sessions

    def _infer_title(self, prompts: List[str], prev: str, cid: str) -> str:
        """Infer title for untitled sessions based on user request keywords."""
        text = " ".join(prompts + [prev]).lower()
        if "face unlock" in text or "howdy" in text or "lock screen" in text:
            return "Howdy Face Unlock & Lockscreen Setup"
        if "seedhe maut" in text or "youtube" in text:
            return "YouTube & Media Assistant"
        if "hyprtasking" in text:
            return "Installing Hyprtasking Plugin"
        if "vmware" in text and "clipboard" in text:
            return "VMware Clipboard Synchronization"
        if "remote" in text or "ecosystem" in text:
            return "Remote Control Suite Ecosystem"
        if cid == CANONICAL_MAIN_SESSION:
            return "Chat AI Assistant"
        if prompts:
            first = prompts[0]
            words = first.split()[:5]
            return " ".join(words).capitalize()
        return f"Session {cid[:8]}"

    def _infer_summary_and_tags(self, title: str, prompts: List[str], prev: str) -> Tuple[str, List[str]]:
        """Generate a human-readable 1-2 sentence summary and search tags."""
        combined = f"{title} {' '.join(prompts)} {prev}".lower()
        tags: List[str] = []

        if "youtube" in combined: tags.extend(["youtube", "video", "music"])
        if "seedhe maut" in combined: tags.extend(["seedhe maut", "luka chuppi", "rap", "song"])
        if "terminal" in combined or "foot" in combined: tags.extend(["terminal", "foot", "console"])
        if "workspace" in combined: tags.extend(["workspace", "hyprland", "layout"])
        if "face unlock" in combined or "howdy" in combined: tags.extend(["face unlock", "howdy", "lockscreen", "pam", "sddm"])
        if "vmware" in combined: tags.extend(["vmware", "virtualization"])
        if "clipboard" in combined: tags.extend(["clipboard", "copy paste", "sync"])
        if "hyprtasking" in combined: tags.extend(["hyprtasking", "hyprpm", "plugin", "overview"])
        if "code" in combined or "vscode" in combined: tags.extend(["vscode", "coding", "editor"])
        if "remote" in combined or "ecosystem" in combined: tags.extend(["remote control", "ecosystem", "ssh", "anydesk"])

        if "chat ai assistant" in title.lower() or "seedhe maut" in combined:
            summary = "Music and video playback on YouTube (Seedhe Maut), multi-workspace layout orchestration, and interactive desktop commands."
        elif "face unlock" in title.lower() or "howdy" in combined:
            summary = "Integration of Howdy facial recognition with Linux PAM, lockscreen QML interface, camera configuration, and SDDM login."
        elif "vmware input" in title.lower() or "vmware tools" in combined:
            summary = "Debugging VMware input capture, cursor integration, USB webcam passthrough, and guest tools installation."
        elif "hyprtasking" in title.lower() or "hyprpm" in combined:
            summary = "Installation and configuration of the Hyprtasking workspace overview plugin via hyprpm with custom keybindings."
        elif "remote system" in title.lower() or "ecosystem" in combined:
            summary = "Architecting the Remote System Control Suite, git repository setup for harshjsh01/ecosystem, and remote access tooling."
        elif "vmware shared" in title.lower() or "clipboard" in combined:
            summary = "Configuring bidirectional VMware host-guest clipboard synchronization daemon and Wayland wl-paste/wl-copy integrations."
        elif "home directory" in title.lower() or "organizing" in combined:
            summary = "Cleanup and organization of files, desktop entries, and scripts in the user's home directory."
        elif "antigravity cli" in title.lower() or "browser" in combined:
            summary = "Setting up Antigravity CLI remote browser access, conversation storage, and command-line execution workflows."
        elif prompts:
            summary = f"Discussion and execution of tasks including: {', '.join(prompts[:3])}."
        else:
            summary = prev[:120] if prev else "General conversation and desktop assistance."

        unique_tags = list(dict.fromkeys(tags))
        return summary, unique_tags

    def _render_markdown(self, sessions: List[Dict[str, Any]], active_cid: str) -> None:
        """Render SESSIONS.md with structured table and session cards."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# 🗂️ B.R.O. (Binary Response Orchestrator) — Antigravity Sessions & Memory Index",
            f"*Last Updated: {now_str} | Single Persistent Desktop Session Management*\n",
            "> [!NOTE]",
            "> Bro tracks all conversations and projects in `~/Work`. You can switch back to any past session at any time",
            "> simply by saying **\"Bro, switch to that session where we did [topic]\"** or using the CLI command `omarchy-assistant sessions switch <id|name>`.\n",
            f"**Currently Active Session:** `{active_cid}`\n",
            "## 📋 Quick Session Overview\n",
            "| Status | Title | Session ID | Last Active | Summary & Topics |",
            "| :---: | :--- | :---: | :--- | :--- |"
        ]

        for s in sessions:
            active_badge = "🟢 **ACTIVE**" if s["is_active"] else "⚪ Idle"
            lines.append(
                f"| {active_badge} | **{s['title']}** | `{s['short_id']}` | {s['date_display']} | {s['summary']} |"
            )

        lines.append("\n---\n\n## 🔍 Detailed Session Registry & Voice Jump Commands\n")

        for idx, s in enumerate(sessions, 1):
            badge = "🟢 **[ACTIVE SESSION]**" if s["is_active"] else f"📁 **[Session #{idx}]**"
            lines.append(f"### {badge} {s['title']}")
            lines.append(f"- **Conversation ID:** `{s['id']}`")
            lines.append(f"- **Last Active:** {s['date_display']} ({s['step_count']} interaction steps)")
            lines.append(f"- **What Was Done:** {s['summary']}")
            if s["tags"]:
                lines.append(f"- **Key Topics / Tags:** `{', '.join(s['tags'])}`")
            if s["prompts_sample"]:
                sample_str = " • ".join([f'\"{p}\"' for p in s["prompts_sample"][:3]])
                lines.append(f"- **Sample Commands:** *{sample_str}*")
            lines.append(f"- **Voice Command to Jump:** *\"Bro, switch to {s['title']}\"* or *\"Bro, switch to session {s['short_id']}\"*")
            lines.append(f"- **CLI Command:** `omarchy-assistant sessions switch {s['short_id']}`\n")

        lines.append("---\n*Maintained automatically by Bro (Omarchy Assistant Daemon).*")

        try:
            self.sessions_md_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"[session_manager] SESSIONS.md write error: {e}")

    def find_session_by_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Find the best matching session based on natural language query using
        token overlap and semantic keyword weighting.
        """
        sessions = self.load_sessions()
        if not sessions:
            sessions = self.sync_sessions()
            if not sessions:
                return None

        clean_q = query.lower().strip()
        clean_q = re.sub(r"\b(switch|jump|back|go|to|the|that|session|where|we|were|was|doing|did|and|or|in|on|chat|conversation|with|about)\b", " ", clean_q)
        q_tokens = [t for t in re.split(r"[^\w\u0900-\u097f]+", clean_q) if len(t) >= 2]

        if not q_tokens:
            return None

        best_session: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for s in sessions:
            score = 0.0
            title_lower = s.get("title", "").lower()
            summary_lower = s.get("summary", "").lower()
            tags = [t.lower() for t in s.get("tags", [])]
            cid = s.get("id", "").lower()
            short_id = s.get("short_id", "").lower()
            prompts_text = " ".join(s.get("prompts_sample", [])).lower()

            # Exact ID match
            for t in q_tokens:
                if t in short_id or t in cid:
                    score += 100.0

            # Title matching
            for t in q_tokens:
                if t in title_lower:
                    score += 15.0
                if any(t in tag for tag in tags):
                    score += 12.0
                if t in summary_lower:
                    score += 6.0
                if t in prompts_text:
                    score += 4.0

            # Special semantic affinities
            if any(k in query.lower() for k in ["seedhe maut", "luka chuppi", "music", "song"]):
                if "seedhe maut" in summary_lower or "seedhe maut" in title_lower or "youtube" in tags:
                    score += 25.0
            if any(k in query.lower() for k in ["face unlock", "face", "howdy", "lockscreen", "sddm"]):
                if "face unlock" in title_lower or "howdy" in tags:
                    score += 30.0
            if any(k in query.lower() for k in ["hyprtasking", "hyprpm"]):
                if "hyprtasking" in title_lower or "hyprtasking" in tags:
                    score += 30.0
            if any(k in query.lower() for k in ["clipboard", "copy paste"]):
                if "clipboard" in title_lower or "clipboard" in tags:
                    score += 25.0
            if any(k in query.lower() for k in ["remote", "ecosystem"]):
                if "remote" in title_lower or "ecosystem" in tags:
                    score += 25.0

            if score > best_score:
                best_score = score
                best_session = s

        if best_score >= 8.0:
            return best_session
        return None

    def load_sessions(self) -> List[Dict[str, Any]]:
        """Load cached sessions from JSON file if available."""
        if self.sessions_json_path.exists():
            try:
                with open(self.sessions_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self.sync_sessions()

    def switch_to_session(self, target: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Switch active session by ID, search query, or 'previous' keyword."""
        sessions = self.load_sessions()
        target_session = None
        target_lower = target.lower().strip()

        # 1. Check for 'previous' / 'prev' / 'pichla'
        if target_lower in ["previous", "prev", "pichla", "pichle", "back"]:
            prev_id = self.get_previous_session_id()
            if prev_id:
                for s in sessions:
                    if s["id"].lower() == prev_id.lower() or s["short_id"].lower() == prev_id.lower():
                        target_session = s
                        break

        # 2. Direct ID match (full or short 8-char hex)
        if not target_session:
            for s in sessions:
                if s["id"].lower() == target_lower or s["short_id"].lower() == target_lower:
                    target_session = s
                    break

        # 3. Direct Title substring match
        if not target_session:
            for s in sessions:
                if target_lower in s.get("title", "").lower():
                    target_session = s
                    break

        # 4. Semantic query match
        if not target_session:
            target_session = self.find_session_by_query(target)

        if not target_session:
            return False, None, f"Could not find a past session matching '{target}'."

        new_cid = target_session["id"]
        title = target_session["title"]
        self.set_active_session_id(new_cid)

        # Refresh SESSIONS.md with new active state
        self.sync_sessions()

        summary_snippet = target_session.get("summary", "")
        if len(summary_snippet) > 80:
            summary_snippet = summary_snippet[:77] + "..."

        spoken = f"Switched to session '{title}', where we worked on {summary_snippet}"
        return True, target_session, spoken


def cli():
    import sys
    sm = SessionManager()
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "list"

    if cmd in ["sync", "refresh", "update"]:
        sessions = sm.sync_sessions(force=True)
        active = sm.get_active_session_id()
        print(f"✅ Successfully indexed {len(sessions)} sessions in ~/Work/SESSIONS.md.")
        print(f"📌 Active session: {active}")

    elif cmd in ["list", "ls", "show"]:
        sessions = sm.load_sessions()
        active = sm.get_active_session_id()
        print(f"\n🗂️  Bro Assistant — Antigravity Sessions ({len(sessions)} total)\n")
        print(f"{'STATUS':<10} {'ID':<10} {'TITLE':<32} {'LAST ACTIVE':<18} {'SUMMARY'}")
        print("-" * 110)
        for s in sessions:
            status = "🟢 ACTIVE" if s["is_active"] else "⚪ Idle"
            short_title = s["title"][:30] + ".." if len(s["title"]) > 32 else s["title"]
            short_sum = s["summary"][:45] + "..." if len(s["summary"]) > 48 else s["summary"]
            print(f"{status:<10} {s['short_id']:<10} {short_title:<32} {s['date_display']:<18} {short_sum}")
        print("-" * 110)
        print(f"\n💡 Full details and jump commands saved in: ~/Work/SESSIONS.md")
        print(f"👉 Jump to a session: omarchy-assistant sessions switch <id|topic>\n")

    elif cmd in ["switch", "jump", "select"]:
        if len(args) < 2:
            print("Error: Target session ID or query required.")
            print("Usage: omarchy-assistant sessions switch <id|topic>")
            sys.exit(1)
        query = " ".join(args[1:])
        success, s, msg = sm.switch_to_session(query)
        if success and s:
            print(f"✅ {msg}")
            print(f"📌 Active conversation: {s['id']} ({s['title']})")
        else:
            print(f"❌ {msg}")
            sys.exit(1)

    elif cmd in ["current", "active", "whoami"]:
        active = sm.get_active_session_id()
        prev = sm.get_previous_session_id()
        sessions = sm.load_sessions()
        curr_session = next((s for s in sessions if s["id"] == active), None)
        title = curr_session["title"] if curr_session else "Unknown"
        print(f"📌 Current Active Session: {active} ({title})")
        if prev:
            prev_session = next((s for s in sessions if s["id"] == prev), None)
            prev_title = prev_session["title"] if prev_session else "Unknown"
            print(f"⏮️  Previous Session: {prev} ({prev_title})")

    elif cmd in ["find", "search"]:
        if len(args) < 2:
            print("Error: Search query required.")
            sys.exit(1)
        query = " ".join(args[1:])
        s = sm.find_session_by_query(query)
        if s:
            print(f"🎯 Best match for '{query}':")
            print(f"   Title: {s['title']} ({s['short_id']})")
            print(f"   Summary: {s['summary']}")
            print(f"   Tags: {', '.join(s['tags'])}")
        else:
            print(f"❌ No matching session found for '{query}'.")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 -m daemon.session_manager [list|sync|switch <target>|current|find <query>]")


if __name__ == "__main__":
    cli()

