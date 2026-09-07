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

        self.state = "idle"  # idle, listening, processing, executing, speaking, meeting_recording
        self.continuous_mode = False
        self._continuous_thread = None
        self.current_transcript = ""
        self.last_action = {}
        self.is_busy = False
        self.lock = threading.Lock()

        self.ipc_server = IPCServer(self.handle_ipc_request)
        self.set_state("idle")

    def set_state(self, state: str, transcript: str = "", action_desc: str = "") -> None:
        """Atomically update state and persist to /tmp/omarchy-assistant-state.json."""
        self.state = state
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
            self.set_state("listening")
            self._continuous_thread = threading.Thread(target=self._run_continuous_loop, daemon=True)
            self._continuous_thread.start()
            return {"status": "started", "message": "Continuous listening started."}

        elif action == "continuous_stop":
            if not self.continuous_mode:
                return {"status": "not_active", "message": "Continuous listening is not active."}
            self.continuous_mode = False
            self.recorder.stop_recording()
            self.set_state("idle")
            return {"status": "stopped", "message": "Continuous listening stopped."}

        elif action == "continuous_toggle":
            if self.continuous_mode:
                self.continuous_mode = False
                self.recorder.stop_recording()
                self.set_state("idle")
                return {"status": "stopped", "message": "Continuous listening stopped."}
            else:
                self.continuous_mode = True
                self.set_state("listening")
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
                # 1. Update state: listening
                greeting = "I'm live, how may I assist you today?"
                self.set_state("listening", transcript=greeting)
                self.executor.send_desktop_notification(
                    {"intent": "assistant_ready", "spoken_response": greeting},
                    success=True
                )
                if self.config.get("sound_feedback", True):
                    self.recorder.play_feedback_tone("start")

                # 2. Record audio with VAD
                wav_path = self.recorder.record_with_vad(
                    max_duration=self.config.get("max_record_seconds", 10.0),
                    silence_timeout=self.config.get("silence_duration_seconds", 1.2),
                    energy_threshold=self.config.get("silence_threshold_energy", 300.0)
                )

                if self.config.get("sound_feedback", True):
                    self.recorder.play_feedback_tone("stop")

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

                # 5. Execute action
                self.set_state(
                    "executing",
                    transcript=transcript,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                # 6. Optional TTS feedback
                if action.get("spoken_response"):
                    self.set_state(
                        "speaking",
                        transcript=transcript,
                        action_desc=action.get("spoken_response", "")
                    )
                    self.tts.speak(action["spoken_response"])

                # If requested to start continuous mode, transition now
                if action.get("intent") == "start_continuous":
                    time.sleep(1.0)
                    self.continuous_mode = True
                    self.set_state("listening")
                    self._continuous_thread = threading.Thread(target=self._run_continuous_loop, daemon=True)
                    self._continuous_thread.start()
                    return

                # Done
                time.sleep(1.0)
                self.set_state("idle")

            except Exception as e:
                print(f"[omarchy-assistant] Pipeline error: {e}", file=sys.stderr)
                self.set_state("idle")
            finally:
                self.is_busy = False

    def _run_continuous_loop(self):
        """Continuously listen and execute commands hands-free until stopped."""
        print("[omarchy-assistant] Continuous listening loop started.")
        self.continuous_mode = True
        greeting = "Continuous listening mode activated. I am listening, Max is at your service."
        self.executor.send_desktop_notification(
            {"intent": "continuous_active", "spoken_response": greeting},
            success=True
        )
        self.tts.speak(greeting, wait=True)

        while self.continuous_mode:
            try:
                # 1. Listening state
                self.set_state("listening")

                # 2. Record audio with VAD
                wav_path = self.recorder.record_with_vad(
                    max_duration=self.config.get("max_record_seconds", 8.0),
                    silence_timeout=self.config.get("silence_duration_seconds", 1.2),
                    energy_threshold=self.config.get("silence_threshold_energy", 300.0)
                )

                if not self.continuous_mode:
                    if wav_path and os.path.exists(wav_path):
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass
                    break

                # If no speech was detected by VAD or no audio file, loop again smoothly
                if not getattr(self.recorder, "last_recording_had_speech", True) or not wav_path or not os.path.exists(wav_path):
                    if wav_path and os.path.exists(wav_path):
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass
                    time.sleep(0.1)
                    continue

                # 3. Transcribe
                self.set_state("processing")

                transcript = self.stt.transcribe(wav_path)
                self.current_transcript = transcript

                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

                if not transcript or not transcript.strip():
                    self.set_state("listening")
                    time.sleep(0.1)
                    continue

                print(f"[omarchy-assistant] [Continuous] Heard: '{transcript}'")

                # Check for stop continuous phrases
                clean_lower = transcript.lower().strip()
                if any(p in clean_lower for p in ["stop listening", "stop continuous", "go to sleep", "chup ho jao", "sleep now", "chup raho", "exit continuous"]):
                    self.continuous_mode = False
                    bye = "Continuous listening stopped. Press Super plus A or say Hey Max when you need me."
                    self.set_state("speaking", transcript=transcript, action_desc=bye)
                    self.tts.speak(bye, wait=True)
                    self.set_state("idle")
                    break

                # 4. Route intent
                action = self.router.route(transcript)
                self.last_action = action

                if action.get("intent") == "stop_continuous":
                    self.continuous_mode = False
                    self.set_state("speaking", transcript=transcript, action_desc=action.get("spoken_response", ""))
                    if action.get("spoken_response"):
                        self.tts.speak(action["spoken_response"], wait=True)
                    self.set_state("idle")
                    break

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
                    self.tts.speak(action["spoken_response"], wait=True)

                # Delay slightly so room acoustic echo clears before opening mic again
                time.sleep(0.4)

            except Exception as e:
                print(f"[omarchy-assistant] Continuous loop error: {e}", file=sys.stderr)
                time.sleep(1.0)

        self.continuous_mode = False
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
