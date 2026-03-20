import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

import websocket

DEFAULT_SETTINGS = {
    "ws_url": "ws://217.216.40.246:9011/ws",
    "reconnect_delay": 2.0,
}
LEGACY_LOCAL_WS_URL = "ws://127.0.0.1:9011/ws"
LEGACY_WRONG_VPS_WS_URL = "ws://217.216.40.246:9010/ws"


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


class Bridge:
    def __init__(self) -> None:
        self.settings_path = self._resolve_settings_path()
        self.settings = self._load_settings()
        self.ws_app: websocket.WebSocketApp | None = None
        self.ws_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.reconnect_lock = threading.Lock()
        self.reconnect_scheduled = False
        self.commands: queue.Queue[dict[str, Any]] = queue.Queue()

    def _resolve_settings_path(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if appdata:
            root = Path(appdata) / "PyChatterWinClient"
        else:
            root = Path.home() / ".pychatter_win_client"
        root.mkdir(parents=True, exist_ok=True)
        return root / "settings.json"

    def _load_settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return dict(DEFAULT_SETTINGS)

        ws_url = str(data.get("ws_url", DEFAULT_SETTINGS["ws_url"])).strip() or DEFAULT_SETTINGS["ws_url"]
        if ws_url in {LEGACY_LOCAL_WS_URL, LEGACY_WRONG_VPS_WS_URL}:
            ws_url = DEFAULT_SETTINGS["ws_url"]
        reconnect_delay = data.get("reconnect_delay", DEFAULT_SETTINGS["reconnect_delay"])
        try:
            reconnect_delay = float(reconnect_delay)
        except Exception:
            reconnect_delay = DEFAULT_SETTINGS["reconnect_delay"]
        reconnect_delay = max(0.5, min(10.0, reconnect_delay))
        return {"ws_url": ws_url, "reconnect_delay": reconnect_delay}

    def _save_settings(self) -> None:
        self.settings_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def connect(self) -> None:
        if self.ws_app and self.ws_app.sock and self.ws_app.sock.connected:
            return

        ws_url = self.settings["ws_url"]

        def on_open(_ws: websocket.WebSocketApp) -> None:
            emit({"event": "status", "value": "Connected"})

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            try:
                packet = json.loads(message)
            except json.JSONDecodeError:
                emit({"event": "status", "value": "Invalid packet from server"})
                return
            emit({"event": "packet", "packet": packet})

        def on_error(_ws: websocket.WebSocketApp, error: Any) -> None:
            emit({"event": "status", "value": f"Connection error: {error}"})

        def on_close(_ws: websocket.WebSocketApp, _code: Any, _reason: Any) -> None:
            emit({"event": "status", "value": "Disconnected"})
            if not self.stop_event.is_set():
                self._schedule_reconnect()

        self.ws_app = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever, daemon=True)
        self.ws_thread.start()

    def disconnect(self) -> None:
        self.stop_event.set()
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception:
                pass
        self.ws_app = None

    def _schedule_reconnect(self) -> None:
        with self.reconnect_lock:
            if self.reconnect_scheduled:
                return
            self.reconnect_scheduled = True

        def worker() -> None:
            time.sleep(float(self.settings.get("reconnect_delay", 2.0)))
            if not self.stop_event.is_set():
                self.connect()
            with self.reconnect_lock:
                self.reconnect_scheduled = False

        threading.Thread(target=worker, daemon=True).start()

    def send_packet(self, packet: dict[str, Any]) -> None:
        if not self.ws_app or not self.ws_app.sock or not self.ws_app.sock.connected:
            emit({"event": "status", "value": "Not connected"})
            return
        try:
            self.ws_app.send(json.dumps(packet))
        except Exception as exc:
            emit({"event": "status", "value": f"Send failed: {exc}"})

    def set_settings(self, partial: dict[str, Any]) -> None:
        ws_url = str(partial.get("ws_url", self.settings["ws_url"]))
        reconnect_delay = partial.get("reconnect_delay", self.settings["reconnect_delay"])
        try:
            reconnect_delay = float(reconnect_delay)
        except Exception:
            reconnect_delay = self.settings["reconnect_delay"]

        self.settings = {
            "ws_url": ws_url.strip() or DEFAULT_SETTINGS["ws_url"],
            "reconnect_delay": max(0.5, min(10.0, reconnect_delay)),
        }
        self._save_settings()
        emit({"event": "settings", "settings": self.settings})

    def run(self) -> None:
        emit({"event": "settings", "settings": self.settings})
        self.connect()

        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                command = json.loads(raw)
            except json.JSONDecodeError:
                emit({"event": "status", "value": "Invalid command JSON"})
                continue

            cmd = command.get("command", "")
            if cmd == "set_settings":
                self.set_settings(command.get("settings", {}))
            elif cmd == "connect":
                self.stop_event.clear()
                self.connect()
            elif cmd == "disconnect":
                self.disconnect()
            elif cmd == "send":
                packet = command.get("packet", {})
                if isinstance(packet, dict):
                    self.send_packet(packet)
            elif cmd == "shutdown":
                self.disconnect()
                break


if __name__ == "__main__":
    bridge = Bridge()
    bridge.run()
