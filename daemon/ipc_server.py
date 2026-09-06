"""
IPC Server for Omarchy Voice Assistant.
Listens on a Unix domain socket for trigger requests from CLI, Hyprland shortcuts, and Quickshell.
"""

import json
import os
import socket
import threading
from typing import Callable, Dict, Any

SOCKET_PATH = "/tmp/omarchy-assistant.sock"


class IPCServer:
    def __init__(self, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.handler = handler
        self.running = False
        self.server_socket = None
        self.thread = None

    def start(self):
        """Start listening on the Unix domain socket."""
        if os.path.exists(SOCKET_PATH):
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(SOCKET_PATH)
        self.server_socket.listen(5)
        # Give user read/write permissions
        os.chmod(SOCKET_PATH, 0o660)

        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                conn, _ = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except Exception:
                if not self.running:
                    break

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                data = conn.recv(4096)
                if not data:
                    return
                req = json.loads(data.decode("utf-8"))
                response = self.handler(req)
                conn.sendall(json.dumps(response).encode("utf-8"))
            except Exception as e:
                err_resp = {"status": "error", "message": str(e)}
                try:
                    conn.sendall(json.dumps(err_resp).encode("utf-8"))
                except Exception:
                    pass

    def stop(self):
        """Stop IPC server and remove socket."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if os.path.exists(SOCKET_PATH):
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass


def send_ipc_command(command: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    """Client utility to send an IPC command to the daemon."""
    if not os.path.exists(SOCKET_PATH):
        raise ConnectionError("Omarchy Assistant daemon is not running (socket not found).")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(SOCKET_PATH)
        client.sendall(json.dumps(command).encode("utf-8"))
        data = client.recv(8192)
        return json.loads(data.decode("utf-8"))
