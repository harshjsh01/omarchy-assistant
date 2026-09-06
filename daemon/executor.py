"""
Command Executor for Omarchy Voice Assistant.
Executes routed actions safely and notifies the user via Quickshell OSD and TTS.
"""

import json
import subprocess
import time
from typing import Any, Dict


class ActionExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the routed action.
        """
        cmd = action.get("command", "").strip()
        spoken = action.get("spoken_response", "")
        start_time = time.time()
        success = True
        output = ""

        if cmd:
            try:
                # Run command in subshell
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8
                )
                output = proc.stdout.strip() or proc.stderr.strip()
                if proc.returncode != 0:
                    success = False
            except Exception as e:
                success = False
                output = str(e)

        elapsed = time.time() - start_time

        # Notify via Omarchy Desktop Notification if enabled
        if self.config.get("notify_osd", True):
            self.send_desktop_notification(action, success)

        return {
            "success": success,
            "output": output,
            "elapsed_ms": int(elapsed * 1000),
            "spoken_response": spoken
        }

    def send_desktop_notification(self, action: Dict[str, Any], success: bool) -> None:
        """Send notification via notify-send."""
        spoken = action.get("spoken_response", "")
        intent = action.get("intent", "Action")
        icon = "dialog-information" if success else "dialog-warning"
        
        try:
            subprocess.Popen([
                "notify-send",
                "-a", "Omarchy Voice Assistant",
                "-i", icon,
                "-t", "3000",
                f"Omarchy Voice: {intent.replace('_', ' ').title()}",
                spoken
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def notify_quickshell(self, state: str, transcript: str = "", action_desc: str = "") -> None:
        """Notify the Omarchy Quickshell plugin via IPC."""
        payload = json.dumps({
            "state": state,
            "transcript": transcript,
            "action": action_desc
        })
        try:
            subprocess.Popen([
                "omarchy-shell", "-q", "assistant", "updateState", payload
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
