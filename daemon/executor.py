"""
Command Executor for Omarchy Voice Assistant with Task Verification & Self-Correction.
Executes routed actions safely, verifies real-world task completion (processes, windows, hardware),
automatically attempts alternative fallback methods upon failure, and reports diagnostic findings.
"""

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Tuple


class ActionExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the routed action, verify the real outcome, and self-correct via fallback if needed.
        """
        cmd = action.get("command", "").strip()
        spoken = action.get("spoken_response", "")
        intent = action.get("intent", "action")
        start_time = time.time()

        if not cmd:
            # Informational / conversational / Antigravity session action without shell execution
            if self.config.get("notify_osd", True):
                self.send_desktop_notification(action, success=True)
            return {
                "success": True,
                "verified": True,
                "output": "",
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "spoken_response": spoken,
                "diagnostic": "Informational action completed"
            }

        # Step 1: Run primary command
        success, output, err = self._run_command(cmd, action)

        # Step 2: Verify task outcome
        verified, verify_reason = self._verify_task(action, cmd, success, output, err)

        # Step 3: Self-Correction / Fallback if verification failed
        alternative_used = False
        if not verified:
            print(f"[omarchy-assistant] Verification failed for '{intent}': {verify_reason}. Attempting self-correction...", flush=True)
            alt_success, alt_output, alt_desc, alt_spoken = self._attempt_alternative(action, cmd, verify_reason)
            if alt_success:
                success = True
                verified = True
                alternative_used = True
                output = alt_output
                if alt_spoken:
                    spoken = alt_spoken
                else:
                    spoken = f"{spoken}. Executed via fallback method."
                print(f"[omarchy-assistant] Self-correction succeeded via alternative: {alt_desc}", flush=True)
            else:
                success = False
                verified = False
                output = f"Primary failed: {verify_reason}. Fallback failed: {alt_desc}"
                spoken = f"I tried to execute {intent.replace('_', ' ')}, but it failed: {verify_reason}. Alternative method also could not complete."
                print(f"[omarchy-assistant] Self-correction failed: {alt_desc}", flush=True)

        elapsed = time.time() - start_time

        # Step 4: Notify via Omarchy Desktop Notification if enabled
        if self.config.get("notify_osd", True):
            self.send_desktop_notification(action, success=verified, custom_message=spoken)

        return {
            "success": success,
            "verified": verified,
            "output": output,
            "elapsed_ms": int(elapsed * 1000),
            "spoken_response": spoken,
            "alternative_used": alternative_used,
            "diagnostic": verify_reason if not verified else "Task verified successfully"
        }

    def _run_command(self, cmd: str, action: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Run command with appropriate detachment and timeout."""
        is_async = (
            action.get("category") == "apps"
            or action.get("is_async", False)
            or cmd.endswith("&")
            or "omarchy launch" in cmd
        )

        # Check if first word of command is a valid executable if not piped/compounded
        clean_cmd = cmd.rstrip("&").strip()
        first_token = clean_cmd.split()[0] if clean_cmd else ""
        if first_token and not any(ch in clean_cmd for ch in ["|", ";", "&", ">", "<", "$", "("]):
            if not shutil.which(first_token) and not os.path.exists(first_token):
                return False, "", f"Command '{first_token}' is not installed on this system"

        try:
            if is_async:
                proc = subprocess.Popen(
                    clean_cmd,
                    shell=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
                # Brief sleep to catch immediate exit / missing executable errors
                time.sleep(0.3)
                ret = proc.poll()
                if ret is not None and ret != 0:
                    err = ""
                    try:
                        err = proc.stderr.read().decode().strip() if proc.stderr else ""
                    except Exception:
                        pass
                    return False, "", err or f"Process exited with code {ret}"
                return True, "Started asynchronously", ""
            else:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=7
                )
                stdout = proc.stdout.strip()
                stderr = proc.stderr.strip()
                if proc.returncode != 0:
                    return False, stdout, stderr or f"Exited with code {proc.returncode}"
                return True, stdout, stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command execution timed out"
        except Exception as e:
            return False, "", str(e)

    def _verify_task(
        self,
        action: Dict[str, Any],
        cmd: str,
        success: bool,
        output: str,
        err: str
    ) -> Tuple[bool, str]:
        """
        Verify whether the task was actually accomplished.
        Checks process tables, Hyprland windows, and hardware states.
        """
        category = action.get("category", "")
        intent = action.get("intent", "")

        # 1. Initial process/spawn failure
        if not success:
            return False, err or "Process execution returned non-zero code"

        # 2. Browser & Web Application launches
        if "browser" in cmd or "https://" in cmd or "http://" in cmd or intent.startswith("open_") or intent.startswith("play_"):
            if "browser" in cmd or any(b in cmd for b in ["chromium", "chrome", "firefox", "brave", "youtube.com", "spotify.com"]):
                # Allow 0.4s for browser process/window to register
                time.sleep(0.4)
                proc_check = subprocess.run(
                    "pgrep -x chromium >/dev/null 2>&1 || pgrep -x chrome >/dev/null 2>&1 || pgrep -x firefox >/dev/null 2>&1 || pgrep -x brave >/dev/null 2>&1",
                    shell=True
                )
                if proc_check.returncode == 0:
                    return True, "Browser process running"
                # Check Hyprland windows
                hl_check = subprocess.run(
                    "hyprctl clients -j 2>/dev/null | grep -iE 'chromium|chrome|firefox|brave' >/dev/null 2>&1",
                    shell=True
                )
                if hl_check.returncode == 0:
                    return True, "Browser window active"
                return False, "Browser process not detected after launch"

        # 3. Terminal launches
        if "terminal" in cmd or intent == "open_terminal":
            time.sleep(0.4)
            proc_check = subprocess.run(
                "pgrep -x foot >/dev/null 2>&1 || pgrep -x alacritty >/dev/null 2>&1 || pgrep -x kitty >/dev/null 2>&1 || pgrep -x ghostty >/dev/null 2>&1",
                shell=True
            )
            if proc_check.returncode == 0:
                return True, "Terminal process running"
            return False, "Terminal process not detected after launch"

        # 3b. Generic Application launches
        if category == "apps" or "omarchy launch" in cmd:
            app_match = re.search(r"omarchy launch (?:app )?([a-zA-Z0-9_\-\.]+)", cmd)
            if not app_match:
                app_match = re.search(r"^([a-zA-Z0-9_\-\.]+)(?:\s+.*)?\s*&?$", cmd)
            if app_match:
                app_name = app_match.group(1).lower().strip()
                if app_name not in ["browser", "terminal"]:
                    time.sleep(0.5)
                    proc_check = subprocess.run(
                        f"pgrep -x '{app_name}' >/dev/null 2>&1 || pidof '{app_name}' >/dev/null 2>&1",
                        shell=True
                    )
                    if proc_check.returncode == 0:
                        return True, f"Application {app_name} process running"
                    hl_check = subprocess.run(
                        f"hyprctl clients -j 2>/dev/null | grep -i '\"class\": \".*{app_name}.*\"' >/dev/null 2>&1",
                        shell=True
                    )
                    if hl_check.returncode == 0:
                        return True, f"Application {app_name} window active"
                    return False, f"Application '{app_name}' failed to launch or window not found"

        # 4. Media Playback Controls (playerctl)
        if category == "media" or "playerctl" in cmd:
            time.sleep(0.2)
            check = subprocess.run(
                "playerctl status 2>&1",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out = (check.stdout + check.stderr).lower()
            if check.returncode != 0 or "no players found" in out or "could not connect" in out or "not found" in out:
                return False, "No active media player found"
            return True, f"Media player state: {out.strip()}"

        # 5. Audio & Volume Controls (wpctl)
        if category == "audio" or "wpctl" in cmd:
            check = subprocess.run(
                "wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null",
                shell=True,
                stdout=subprocess.PIPE,
                text=True
            )
            if check.returncode == 0 and check.stdout.strip():
                return True, f"Audio volume verified: {check.stdout.strip()}"
            return False, "Failed to query audio sink volume"

        # 6. Hyprland Window Manager Dispatches
        if category == "hyprland" or "hyprctl" in cmd:
            if output and "ok" in output.lower():
                return True, "Hyprland dispatch confirmed"
            elif err:
                return False, f"Hyprland error: {err}"
            return True, "Hyprland command dispatched"

        # 7. Brightness Controls
        if category == "display" or "brightnessctl" in cmd:
            if success:
                return True, "Brightness updated"
            return False, err or "Brightnessctl failed"

        # 8. Generic verification for other commands
        if success:
            return True, "Command executed successfully"
        return False, err or "Execution failed"

    def _attempt_alternative(
        self,
        action: Dict[str, Any],
        failed_cmd: str,
        reason: str
    ) -> Tuple[bool, str, str, Optional[str]]:
        """
        Attempt an alternative method or fallback when the primary execution fails.
        Returns (success, output, description, spoken_response).
        """
        intent = action.get("intent", "")
        category = action.get("category", "")

        # Fallback 1: Browser or Web URL Launch Failed
        if "browser" in failed_cmd or "https://" in failed_cmd or "http://" in failed_cmd or intent in ["open_youtube", "play_youtube", "open_spotify", "play_spotify"]:
            # Extract URL if present
            url_match = re.search(r"'(https?://[^']+)'|\"(https?://[^\"]+)\"|(https?://[^\s]+)", failed_cmd)
            target_url = ""
            if url_match:
                target_url = url_match.group(1) or url_match.group(2) or url_match.group(3)

            if not target_url:
                if "youtube" in intent:
                    target_url = "https://youtube.com"
                elif "spotify" in intent:
                    target_url = "https://open.spotify.com"
                else:
                    target_url = "https://google.com"

            # Alternative candidates
            browser_fallbacks = [
                f"chromium '{target_url}' &",
                f"google-chrome-stable '{target_url}' &",
                f"firefox '{target_url}' &",
                f"xdg-open '{target_url}' &"
            ]

            for fb_cmd in browser_fallbacks:
                bin_name = fb_cmd.split()[0]
                if shutil.which(bin_name):
                    print(f"[omarchy-assistant] Trying fallback browser command: {fb_cmd}", flush=True)
                    s, out, err = self._run_command(fb_cmd, {"category": "apps", "is_async": True})
                    time.sleep(0.5)
                    v, r = self._verify_task(action, fb_cmd, s, out, err)
                    if v:
                        return True, out, f"Launched via fallback {bin_name}", f"Opened in {bin_name} via fallback."

            return False, "", "All browser fallback launchers failed", None

        # Fallback 2: Terminal Launch Failed
        if "terminal" in failed_cmd or intent == "open_terminal":
            term_fallbacks = ["foot &", "alacritty &", "kitty &", "ghostty &", "xterm &"]
            for fb_cmd in term_fallbacks:
                bin_name = fb_cmd.split()[0]
                if shutil.which(bin_name):
                    s, out, err = self._run_command(fb_cmd, {"category": "apps", "is_async": True})
                    time.sleep(0.5)
                    v, r = self._verify_task(action, fb_cmd, s, out, err)
                    if v:
                        return True, out, f"Launched terminal via {bin_name}", f"Opened {bin_name} terminal via fallback."

            return False, "", "All terminal fallback launchers failed", None

        # Fallback 3: Media Play Failed because no active player exists
        if intent == "media_play" and "No active media player found" in reason:
            # User wanted to play music, but no player is running. Auto-launch YouTube!
            print("[omarchy-assistant] No active player found. Auto-launching YouTube for music playback...", flush=True)
            yt_cmd = "omarchy launch browser 'https://youtube.com' || chromium 'https://youtube.com' &"
            s, out, err = self._run_command(yt_cmd, {"category": "apps", "is_async": True})
            time.sleep(0.6)
            v, r = self._verify_task({"category": "apps"}, yt_cmd, s, out, err)
            if v:
                return True, out, "Auto-launched YouTube in browser", "No active media player was running, so I opened YouTube for you."
            return False, "", "Failed to open YouTube as fallback music source", None

        # Fallback 4: Volume / Audio Controls Failed
        if category == "audio" or "wpctl" in failed_cmd:
            if "5%+" in failed_cmd:
                alt_cmd = "pamixer -i 5 2>/dev/null || amixer sset Master 5%+ 2>/dev/null"
            elif "5%-" in failed_cmd:
                alt_cmd = "pamixer -d 5 2>/dev/null || amixer sset Master 5%- 2>/dev/null"
            else:
                alt_cmd = "pamixer -t 2>/dev/null || amixer sset Master toggle 2>/dev/null"

            s, out, err = self._run_command(alt_cmd, {"category": "audio"})
            if s:
                return True, out, "Executed volume control via alsa/pamixer fallback", "Volume adjusted via secondary audio controller."

            return False, "", "Audio fallback controllers failed", None

        # Fallback 5: Generic Application Launch Failed
        m = re.search(r"omarchy launch (?:app )?([a-zA-Z0-9_\-\.]+)", failed_cmd)
        if m:
            app_name = m.group(1)
            direct_cmd = f"{app_name} &"
            if shutil.which(app_name):
                s, out, err = self._run_command(direct_cmd, {"category": "apps", "is_async": True})
                time.sleep(0.5)
                v, r = self._verify_task(action, direct_cmd, s, out, err)
                if v:
                    return True, out, f"Launched {app_name} directly", f"Opened {app_name} directly."

        return False, "", f"No viable alternative found for command: {failed_cmd}", None

    def send_desktop_notification(
        self,
        action: Dict[str, Any],
        success: bool,
        custom_message: Optional[str] = None
    ) -> None:
        """Send notification via notify-send with informative title and icon."""
        message = custom_message or action.get("spoken_response", "")
        intent = action.get("intent", "Action")
        icon = "dialog-information" if success else "dialog-warning"

        try:
            subprocess.Popen([
                "notify-send",
                "-a", "Omarchy Voice Assistant",
                "-i", icon,
                "-t", "3500",
                f"Omarchy Voice: {intent.replace('_', ' ').title()}",
                message
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
