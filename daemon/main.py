"""
Main Daemon entrypoint for Omarchy Voice Assistant.
Coordinates audio recording, speech recognition, intent routing, and execution.
"""

import argparse
import json
import os
import sys
import threading
import time
from typing import Any, Dict

from .audio_recorder import AudioRecorder
from .config import load_config, save_config
from .command_router import CommandRouter
from .executor import ActionExecutor
from .ipc_server import IPCServer
from .meeting_transcriber import MeetingRecorder
from .stt_engine import get_stt_engine
from .tts_engine import TTSEngine


class AssistantDaemon:
    def __init__(self):
        self.config = load_config()
        self.recorder = AudioRecorder(
            sample_rate=self.config.get("sample_rate", 16000),
            max_duration=self.config.get("max_record_seconds", 12.0)
        )
        self.stt = get_stt_engine(self.config)
        self.router = CommandRouter(self.config)
        self.executor = ActionExecutor(self.config)
        self.tts = TTSEngine(self.config)
        self.meeting = MeetingRecorder(self.config, self.stt, self.router)

        self.state = "idle"  # idle, listening, processing, executing, speaking, meeting_recording, continuous_standby
        self.continuous_mode = False
        self._continuous_thread = None
        self._dialogue_active_until = 0.0
        self._last_action_desc = ""
        self.current_transcript = ""
        self.last_action = {}
        self.is_busy = False
        self.lock = threading.Lock()

        self.ipc_server = IPCServer(self.handle_ipc_request)
        self.set_state("idle")

    def set_state(self, state: str, transcript: str = "", action_desc: str = "") -> None:
        """Atomically update state and persist to /tmp/omarchy-assistant-state.json."""
        if (state == self.state and 
            (not transcript or transcript == self.current_transcript) and
            action_desc == self._last_action_desc):
            return

        self.state = state
        self._last_action_desc = action_desc
        if transcript:
            self.current_transcript = transcript
        state_data = {
            "state": state,
            "continuous_mode": self.continuous_mode,
            "transcript": self.current_transcript,
            "last_action": action_desc or (self.last_action.get("spoken_response", "") if isinstance(self.last_action, dict) else ""),
            "stt_engine": self.stt.__class__.__name__,
            "tts_enabled": self.tts.enabled,
            "timestamp": time.time()
        }
        try:
            tmp = "/tmp/omarchy-assistant-state.json.tmp"
            with open(tmp, "w") as f:
                json.dump(state_data, f)
            os.replace(tmp, "/tmp/omarchy-assistant-state.json")
        except Exception:
            pass
        self.executor.notify_quickshell(state, self.current_transcript, action_desc)

    def handle_ipc_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch IPC requests."""
        action = req.get("action", "")

        if action == "status":
            return {
                "state": self.state,
                "continuous_mode": self.continuous_mode,
                "transcript": self.current_transcript,
                "last_action": self.last_action,
                "stt_engine": self.stt.__class__.__name__
            }

        elif action == "listen":
            if self.continuous_mode:
                return {"status": "active", "message": "Continuous listening mode is already active."}
            if self.is_busy:
                return {"status": "busy", "message": "Already processing an instruction."}

            # Run listening flow in background thread
            threading.Thread(target=self._run_voice_pipeline, daemon=True).start()
            return {"status": "started", "message": "Listening started."}

        elif action == "stop_listening":
            if self.state == "listening":
                self.recorder.stop_recording()
                self.set_state("idle")
                return {"status": "stopped"}
            return {"status": "not_listening"}

        elif action == "toggle_tts":
            self.tts.enabled = not self.tts.enabled
            self.config["tts_enabled"] = self.tts.enabled
            save_config(self.config)
            self.set_state(self.state)
            return {"status": "ok", "tts_enabled": self.tts.enabled}

        elif action == "continuous_start":
            if self.continuous_mode:
                return {"status": "already_active", "message": "Continuous listening is already active."}
            self.continuous_mode = True
            self.set_state("continuous_standby")
            self._continuous_thread = threading.Thread(target=self._run_continuous_loop, daemon=True)
            self._continuous_thread.start()
            return {"status": "started", "message": "Continuous listening started."}

        elif action == "continuous_stop":
            if not self.continuous_mode:
                return {"status": "not_active", "message": "Continuous listening is not active."}
            self.continuous_mode = False
            self.recorder.stop_continuous_stream()
            self.recorder.stop_recording()
            self.set_state("idle")
            return {"status": "stopped", "message": "Continuous listening stopped."}

        elif action == "continuous_toggle":
            if self.continuous_mode:
                self.continuous_mode = False
                self.recorder.stop_continuous_stream()
                self.recorder.stop_recording()
                self.set_state("idle")
                return {"status": "stopped", "message": "Continuous listening stopped."}
            else:
                self.continuous_mode = True
                self.set_state("continuous_standby")
                self._continuous_thread = threading.Thread(target=self._run_continuous_loop, daemon=True)
                self._continuous_thread.start()
                return {"status": "started", "message": "Continuous listening started."}

        elif action == "continuous_status":
            return {"continuous_mode": self.continuous_mode, "state": self.state}

        elif action == "execute":
            # Execute text directly without recording
            text = req.get("text", "")
            if not text:
                return {"status": "error", "message": "No text provided."}

            threading.Thread(target=self._run_text_pipeline, args=(text,), daemon=True).start()
            return {"status": "started", "text": text}

        elif action == "meeting_start":
            res = self.meeting.start_meeting()
            if res.get("status") == "started":
                self.set_state("meeting_recording", action_desc="Recording Meeting (Mic + Speakers)")
            return res

        elif action == "meeting_stop":
            self.set_state("processing", action_desc="Transcribing Meeting Audio...")
            res = self.meeting.stop_and_transcribe()
            self.set_state("idle")
            return res

        elif action == "meeting_status":
            return self.meeting.status()

        return {"status": "error", "message": f"Unknown action '{action}'"}

    def _run_voice_pipeline(self):
        with self.lock:
            self.is_busy = True
            try:
                # 1. Spoken greeting: speak aloud before opening mic
                greeting = "I'm live, how may I assist you today?"
                self.set_state("speaking", transcript=greeting, action_desc=greeting)
                self.executor.send_desktop_notification(
                    {"intent": "assistant_ready", "spoken_response": greeting},
                    success=True
                )
                if self.tts.enabled:
                    self.tts.speak(greeting, wait=True)

                # 2. Record audio with VAD
                self.set_state("listening")
                wav_path = self.recorder.record_with_vad(
                    max_duration=self.config.get("max_record_seconds", 12.0),
                    silence_timeout=self.config.get("silence_duration_seconds", 1.2),
                    energy_threshold=self.config.get("silence_threshold_energy", 1000.0)
                )

                if not wav_path or not os.path.exists(wav_path):
                    self.set_state("idle")
                    return

                # 3. Update state: processing STT
                self.set_state("processing")

                transcript = self.stt.transcribe(wav_path)
                self.current_transcript = transcript

                # Clean up temporary audio file
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

                if not transcript or not transcript.strip():
                    self.set_state("idle")
                    return

                # 4. Route intent
                action = self.router.route(transcript)
                self.last_action = action

                # Play ting chime ONLY when there is output
                if action.get("spoken_response") or action.get("command"):
                    if self.config.get("sound_feedback", True):
                        self.recorder.play_feedback_tone("output")

                # 5. Execute action
                self.set_state(
                    "executing",
                    transcript=transcript,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                # 6. TTS feedback
                if action.get("spoken_response"):
                    self.set_state(
                        "speaking",
                        transcript=transcript,
                        action_desc=action.get("spoken_response", "")
                    )
                    if self.tts.enabled:
                        self.tts.speak(action["spoken_response"], wait=True)

                # If requested to start continuous mode, transition now
                if action.get("intent") == "start_continuous":
                    time.sleep(0.5)
                    self.continuous_mode = True
                    self._continuous_thread = threading.Thread(target=self._run_continuous_loop, daemon=True)
                    self._continuous_thread.start()
                    return

                # Done
                time.sleep(0.5)
                self.set_state("idle")

            except Exception as e:
                print(f"[omarchy-assistant] Pipeline error: {e}", file=sys.stderr)
                self.set_state("idle")
            finally:
                self.is_busy = False

    def _is_addressed_to_max(self, transcript: str) -> bool:
        """
        Check if speech during continuous mode is directed at Max or is an intentional action/query.
        """
        import re
        clean = transcript.lower().strip()
        norm = re.sub(r"[^\w\s]", " ", clean).strip()
        if not norm or len(norm.split()) == 0:
            return False

        # Stop commands are always accepted
        if any(p in norm for p in ["stop listening", "stop continuous", "go to sleep", "chup ho jao", "sleep now", "chup raho", "exit continuous"]):
            return True

        # If user is in an active conversational window (within 30s of previous turn)
        if time.time() < getattr(self, "_dialogue_active_until", 0.0):
            return True

        # Wake phrases, names, and liveness inquiries
        wake_patterns = [
            r"\b(hey\s+max|ok\s+max|hello\s+max|hi\s+max|arrey\s+max|suno\s+max|namaste\s+max|a\s+max|hey\s+marks|hey\s+macs)\b",
            r"\bmax\b",
            r"\b(are\s+you\s+alive|are\s+you\s+there|can\s+you\s+hear\s+me|you\s+alive|zinda\s+ho|sun\s+rahe\s+ho|kya\s+tum\s+zinda\s+ho|kya\s+tum\s+sun\s+rahe\s+ho)\b",
        ]
        for pat in wake_patterns:
            if re.search(pat, norm):
                return True

        # Direct action and control commands (open, play, launch, monitor, background, etc.)
        action_keywords = [
            "open", "launch", "play", "pause", "resume", "stop", "close", "kill",
            "volume", "mute", "unmute", "brightness", "switch", "workspace",
            "screenshot", "capture", "run", "start", "remember", "remind", "reminder",
            "monitor", "activity", "background", "status", "process", "task", "health",
            "kholo", "band", "chalao", "bajao", "roko", "badhao", "kam karo", "dikhao",
            "yaad", "kaam", "dekh", "sun"
        ]
        if any(re.search(rf"\b{re.escape(k)}\b", norm) for k in action_keywords):
            return True

        # Complex reasoning/brainstorming/coding queries intended for AI
        complex_keywords = [
            "brainstorm", "project", "idea", "plan", "build", "create", "code", "develop",
            "documentation", "docs", "write", "design", "system", "architecture", "script",
            "how", "why", "what", "who", "where", "when", "can you", "could you", "tell me",
            "explain", "help", "think", "suggest", "search for",
            "kya", "kyun", "kaise", "batao", "banao", "socho", "sikhao", "samjhao"
        ]
        words = norm.split()
        if any(k in norm for k in complex_keywords) and len(words) >= 2:
            return True

        return False

    def _run_continuous_loop(self):
        """Continuously listen and execute commands hands-free until stopped."""
        print("[omarchy-assistant] Continuous listening loop started.")
        self.continuous_mode = True
        greeting = "Continuous listening mode activated. I am listening, Max is at your service."
        self.set_state("speaking", transcript=greeting, action_desc=greeting)
        self.executor.send_desktop_notification(
            {"intent": "continuous_active", "spoken_response": greeting},
            success=True
        )
        if self.tts.enabled:
            self.tts.speak(greeting, wait=True)

        self.recorder.start_continuous_stream()
        self.set_state("continuous_standby")

        while self.continuous_mode:
            try:
                # 1. Standby state (green microphone icon in bar)
                self.is_busy = False
                self.set_state("continuous_standby")

                # Callback when user starts speaking -> switch UI immediately to animated blue dots
                def on_speech_start_callback():
                    if self.continuous_mode:
                        self.set_state("listening")

                # 2. Record next utterance from persistent stream
                wav_path = self.recorder.listen_turn(
                    silence_timeout=self.config.get("silence_duration_seconds", 1.1),
                    energy_threshold=self.config.get("silence_threshold_energy", 1050.0),
                    on_speech_start=on_speech_start_callback,
                    is_active=lambda: self.continuous_mode,
                    max_duration=self.config.get("max_record_seconds", 12.0)
                )

                if not self.continuous_mode:
                    if wav_path and os.path.exists(wav_path):
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass
                    break

                if not wav_path or not os.path.exists(wav_path):
                    self.set_state("continuous_standby")
                    time.sleep(0.05)
                    continue

                # User spoke: transition to processing (animated yellow dots)
                self.is_busy = True
                self.set_state("processing")

                transcript = self.stt.transcribe(wav_path)
                self.current_transcript = transcript

                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

                if not transcript or not transcript.strip():
                    self.set_state("continuous_standby")
                    time.sleep(0.05)
                    continue

                print(f"[omarchy-assistant] [Continuous] Heard: '{transcript}'")

                # Check for stop continuous phrases
                clean_lower = transcript.lower().strip()
                if any(p in clean_lower for p in ["stop listening", "stop continuous", "go to sleep", "chup ho jao", "sleep now", "chup raho", "exit continuous"]):
                    self.continuous_mode = False
                    self.recorder.stop_continuous_stream()
                    bye = "Continuous listening stopped. Say Hey Max when you need me."
                    self.set_state("speaking", transcript=transcript, action_desc=bye)
                    if self.tts.enabled:
                        self.tts.speak(bye, wait=True)
                    self.set_state("idle")
                    break

                # In continuous mode: only route speech if addressed to Max or an intentional command/query
                if not self._is_addressed_to_max(transcript):
                    print(f"[omarchy-assistant] [Continuous] Ignored non-command speech in standby: '{transcript}'")
                    self.set_state("continuous_standby")
                    time.sleep(0.05)
                    continue

                # Refresh dialogue active timer (30 seconds for natural follow-ups without repeating Hey Max)
                self._dialogue_active_until = time.time() + 30.0

                # 4. Route intent
                action = self.router.route(transcript)
                self.last_action = action

                if action.get("intent") == "stop_continuous":
                    self.continuous_mode = False
                    self.recorder.stop_continuous_stream()
                    self.set_state("speaking", transcript=transcript, action_desc=action.get("spoken_response", ""))
                    if action.get("spoken_response") and self.tts.enabled:
                        self.tts.speak(action["spoken_response"], wait=True)
                    self.set_state("idle")
                    break

                # Play ting chime ONLY when there is output
                if action.get("spoken_response") or action.get("command"):
                    if self.config.get("sound_feedback", True):
                        self.recorder.play_feedback_tone("output")

                # 5. Execute action
                self.set_state(
                    "executing",
                    transcript=transcript,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                # 6. Speak response synchronously so microphone does not pick up Max's own voice
                if action.get("spoken_response"):
                    self.set_state(
                        "speaking",
                        transcript=transcript,
                        action_desc=action.get("spoken_response", "")
                    )
                    if self.tts.enabled:
                        self.tts.speak(action["spoken_response"], wait=True)

                # Delay slightly so room acoustic echo clears, and drain any speaker audio from the pipe
                time.sleep(0.4)
                self.recorder.drain_stream()
                self.set_state("continuous_standby")

            except Exception as e:
                print(f"[omarchy-assistant] Continuous loop error: {e}", file=sys.stderr)
                self.set_state("continuous_standby")
                time.sleep(0.5)

        self.continuous_mode = False
        self.recorder.stop_continuous_stream()
        self.set_state("idle")

    def _run_text_pipeline(self, text: str):
        with self.lock:
            self.is_busy = True
            try:
                self.set_state("processing", transcript=text)

                action = self.router.route(text)
                self.last_action = action

                self.set_state(
                    "executing",
                    transcript=text,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                if action.get("spoken_response"):
                    self.set_state(
                        "speaking",
                        transcript=text,
                        action_desc=action.get("spoken_response", "")
                    )
                    self.tts.speak(action["spoken_response"])

                time.sleep(1.0)
                self.set_state("idle")

            finally:
                self.is_busy = False

    def run(self):
        """Start the daemon service."""
        print("[omarchy-assistant] Starting Omarchy Voice Assistant Daemon...")
        print(f"[omarchy-assistant] STT Engine: {self.stt.__class__.__name__}")
        self.ipc_server.start()
        print(f"[omarchy-assistant] IPC Server listening on {self.ipc_server.server_socket.getsockname() if self.ipc_server.server_socket else '/tmp/omarchy-assistant.sock'}")
        
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\n[omarchy-assistant] Shutting down...")
            self.ipc_server.stop()


def main():
    parser = argparse.ArgumentParser(description="Omarchy Voice Assistant Daemon")
    parser.add_argument("--test-text", type=str, help="Simulate a voice command directly via text")
    args = parser.parse_args()

    daemon = AssistantDaemon()

    if args.test_text:
        print(f"Routing text command: '{args.test_text}'")
        action = daemon.router.route(args.test_text)
        print("Routed action:", action)
        res = daemon.executor.execute(action)
        print("Execution result:", res)
        sys.exit(0)

    daemon.run()


if __name__ == "__main__":
    main()
