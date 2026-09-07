"""
Main Daemon entrypoint for Omarchy Voice Assistant.
Coordinates audio recording, speech recognition, intent routing, and execution.
"""

import argparse
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
        self.current_transcript = ""
        self.last_action = {}
        self.is_busy = False
        self.lock = threading.Lock()

        self.ipc_server = IPCServer(self.handle_ipc_request)

    def handle_ipc_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch IPC requests."""
        action = req.get("action", "")

        if action == "status":
            return {
                "state": self.state,
                "transcript": self.current_transcript,
                "last_action": self.last_action,
                "stt_engine": self.stt.__class__.__name__
            }

        elif action == "listen":
            if self.is_busy:
                return {"status": "busy", "message": "Already processing an instruction."}

            # Run listening flow in background thread
            threading.Thread(target=self._run_voice_pipeline, daemon=True).start()
            return {"status": "started", "message": "Listening started."}

        elif action == "stop_listening":
            if self.state == "listening":
                self.recorder.stop_recording()
                return {"status": "stopped"}
            return {"status": "not_listening"}

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
                self.state = "meeting_recording"
                self.executor.notify_quickshell("meeting_recording", action_desc="Recording Meeting (Mic + Speakers)")
            return res

        elif action == "meeting_stop":
            self.executor.notify_quickshell("processing", action_desc="Transcribing Meeting Audio...")
            res = self.meeting.stop_and_transcribe()
            self.state = "idle"
            self.executor.notify_quickshell("idle")
            return res

        elif action == "meeting_status":
            return self.meeting.status()

        return {"status": "error", "message": f"Unknown action '{action}'"}

    def _run_voice_pipeline(self):
        with self.lock:
            self.is_busy = True
            try:
                # 1. Update state: listening
                self.state = "listening"
                self.current_transcript = ""
                greeting = "I'm live, how may I assist you today?"
                self.executor.notify_quickshell("listening", transcript=greeting)
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
                    self.state = "idle"
                    self.executor.notify_quickshell("idle")
                    return

                # 3. Update state: processing STT
                self.state = "processing"
                self.executor.notify_quickshell("processing")

                transcript = self.stt.transcribe(wav_path)
                self.current_transcript = transcript

                # Clean up temporary audio file
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

                if not transcript or not transcript.strip():
                    self.state = "idle"
                    self.executor.notify_quickshell("idle")
                    return

                # 4. Route intent
                action = self.router.route(transcript)
                self.last_action = action

                # 5. Execute action
                self.state = "executing"
                self.executor.notify_quickshell(
                    "executing",
                    transcript=transcript,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                # 6. Optional TTS feedback
                if action.get("spoken_response"):
                    self.state = "speaking"
                    self.tts.speak(action["spoken_response"])

                # Done
                time.sleep(1.0)
                self.state = "idle"
                self.executor.notify_quickshell("idle")

            except Exception as e:
                print(f"[omarchy-assistant] Pipeline error: {e}", file=sys.stderr)
                self.state = "idle"
                self.executor.notify_quickshell("idle")
            finally:
                self.is_busy = False

    def _run_text_pipeline(self, text: str):
        with self.lock:
            self.is_busy = True
            try:
                self.current_transcript = text
                self.state = "processing"
                self.executor.notify_quickshell("processing", transcript=text)

                action = self.router.route(text)
                self.last_action = action

                self.state = "executing"
                self.executor.notify_quickshell(
                    "executing",
                    transcript=text,
                    action_desc=action.get("spoken_response", "")
                )

                result = self.executor.execute(action)

                if action.get("spoken_response"):
                    self.tts.speak(action["spoken_response"])

                time.sleep(1.0)
                self.state = "idle"
                self.executor.notify_quickshell("idle")

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
