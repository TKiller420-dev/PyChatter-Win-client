import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, simpledialog
import websocket


DEFAULT_WS_URL = "ws://127.0.0.1:9011/ws"
DEFAULT_RECONNECT_DELAY = 2.0


@dataclass
class AppSettings:
    ws_url: str = DEFAULT_WS_URL
    reconnect_delay: float = DEFAULT_RECONNECT_DELAY


class PyChatterClient(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("PyChatter Desktop")
        self.geometry("1280x780")
        self.minsize(980, 620)

        self.settings_path = self._resolve_settings_path()
        self.settings = self._load_settings()

        self.ws_app: websocket.WebSocketApp | None = None
        self.ws_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.reconnect_lock = threading.Lock()
        self.reconnect_scheduled = False

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.username = ""
        self.role = "member"
        self.current_channel = "general"
        self.channels: list[str] = []
        self.users: list[str] = []
        self.selected_user = ""
        self.is_authed = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(120, self._pump_events)
        self._connect()

    def _resolve_settings_path(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if appdata:
            root = Path(appdata) / "PyChatterWinClient"
        else:
            root = Path.home() / ".pychatter_win_client"
        root.mkdir(parents=True, exist_ok=True)
        return root / "settings.json"

    def _load_settings(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()

        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return AppSettings()

        ws_url = str(data.get("ws_url", DEFAULT_WS_URL)).strip() or DEFAULT_WS_URL
        reconnect_delay = float(data.get("reconnect_delay", DEFAULT_RECONNECT_DELAY))
        reconnect_delay = max(0.5, min(10.0, reconnect_delay))
        return AppSettings(ws_url=ws_url, reconnect_delay=reconnect_delay)

    def _save_settings(self) -> None:
        payload = {
            "ws_url": self.settings.ws_url,
            "reconnect_delay": self.settings.reconnect_delay,
        }
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.topbar = ctk.CTkFrame(self, corner_radius=0, height=44)
        self.topbar.grid(row=0, column=0, sticky="nsew")
        self.topbar.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkLabel(self.topbar, text="PyChatter", font=ctk.CTkFont(size=17, weight="bold"))
        brand.grid(row=0, column=0, padx=14, pady=10)

        self.connection_state_label = ctk.CTkLabel(self.topbar, text="Connecting...", text_color="#d8dee9")
        self.connection_state_label.grid(row=0, column=1, padx=8, pady=10, sticky="w")

        self.reconnect_btn = ctk.CTkButton(
            self.topbar,
            text="Reconnect",
            width=110,
            command=self._manual_reconnect,
        )
        self.reconnect_btn.grid(row=0, column=2, padx=(0, 12), pady=8)

        self.auth_view = ctk.CTkFrame(self, corner_radius=0)
        self.auth_view.grid(row=1, column=0, sticky="nsew")
        self.auth_view.grid_columnconfigure(0, weight=1)
        self.auth_view.grid_rowconfigure(0, weight=1)

        auth_card = ctk.CTkFrame(self.auth_view, width=500, height=500)
        auth_card.grid(row=0, column=0)
        auth_card.grid_propagate(False)
        auth_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(auth_card, text="Welcome to PyChatter", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, padx=26, pady=(26, 10), sticky="w"
        )
        ctk.CTkLabel(
            auth_card,
            text="Sign in or register, then join your channels.",
            text_color="#aab0c0",
        ).grid(row=1, column=0, padx=26, pady=(0, 16), sticky="w")

        self.auth_mode = ctk.StringVar(value="login")
        mode_menu = ctk.CTkOptionMenu(auth_card, values=["login", "register"], variable=self.auth_mode)
        mode_menu.grid(row=2, column=0, padx=26, pady=(0, 14), sticky="ew")

        self.username_entry = ctk.CTkEntry(auth_card, placeholder_text="Username")
        self.username_entry.grid(row=3, column=0, padx=26, pady=8, sticky="ew")

        self.password_entry = ctk.CTkEntry(auth_card, placeholder_text="Password", show="*")
        self.password_entry.grid(row=4, column=0, padx=26, pady=8, sticky="ew")

        self.ws_url_entry = ctk.CTkEntry(auth_card, placeholder_text="WebSocket URL")
        self.ws_url_entry.insert(0, self.settings.ws_url)
        self.ws_url_entry.grid(row=5, column=0, padx=26, pady=(16, 8), sticky="ew")

        self.reconnect_delay_entry = ctk.CTkEntry(auth_card, placeholder_text="Reconnect delay seconds")
        self.reconnect_delay_entry.insert(0, str(self.settings.reconnect_delay))
        self.reconnect_delay_entry.grid(row=6, column=0, padx=26, pady=8, sticky="ew")

        self.auth_status = ctk.CTkLabel(auth_card, text="", text_color="#ff8a9c")
        self.auth_status.grid(row=7, column=0, padx=26, pady=(6, 6), sticky="w")

        auth_btns = ctk.CTkFrame(auth_card, fg_color="transparent")
        auth_btns.grid(row=8, column=0, padx=26, pady=(10, 14), sticky="ew")
        auth_btns.grid_columnconfigure((0, 1), weight=1)

        save_btn = ctk.CTkButton(auth_btns, text="Save Connection", command=self._save_connection_settings)
        save_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        submit_btn = ctk.CTkButton(auth_btns, text="Continue", command=self._submit_auth)
        submit_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self.app_view = ctk.CTkFrame(self, corner_radius=0)
        self.app_view.grid(row=1, column=0, sticky="nsew")
        self.app_view.grid_columnconfigure(0, weight=0)
        self.app_view.grid_columnconfigure(1, weight=1)
        self.app_view.grid_columnconfigure(2, weight=0)
        self.app_view.grid_rowconfigure(0, weight=1)

        self.channels_pane = ctk.CTkFrame(self.app_view, width=250)
        self.channels_pane.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.channels_pane.grid_propagate(False)
        self.channels_pane.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.channels_pane, text="Text Channels", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        self.channels_listbox = tk.Listbox(
            self.channels_pane,
            bg="#1f2937",
            fg="#e5e7eb",
            selectbackground="#2563eb",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        self.channels_listbox.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.channels_listbox.bind("<<ListboxSelect>>", self._on_channel_select)

        channel_buttons = ctk.CTkFrame(self.channels_pane, fg_color="transparent")
        channel_buttons.grid(row=2, column=0, padx=12, pady=(4, 12), sticky="ew")
        channel_buttons.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(channel_buttons, text="New Channel", command=self._new_channel).grid(
            row=0, column=0, padx=(0, 6), sticky="ew"
        )
        ctk.CTkButton(channel_buttons, text="Refresh Users", command=lambda: self._send({"type": "who"})).grid(
            row=0, column=1, padx=(6, 0), sticky="ew"
        )

        center = ctk.CTkFrame(self.app_view)
        center.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(center)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)

        self.channel_title_label = ctk.CTkLabel(header, text="#general", font=ctk.CTkFont(size=20, weight="bold"))
        self.channel_title_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.role_badge = ctk.CTkLabel(header, text="member", text_color="#a7f3d0")
        self.role_badge.grid(row=0, column=1, padx=8, pady=8, sticky="e")

        self.messages_text = tk.Text(
            center,
            bg="#111827",
            fg="#e5e7eb",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            state="disabled",
            font=("Segoe UI", 10),
        )
        self.messages_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)

        self.typing_label = ctk.CTkLabel(center, text="", text_color="#9ca3af")
        self.typing_label.grid(row=2, column=0, sticky="w", padx=12)

        compose = ctk.CTkFrame(center)
        compose.grid(row=3, column=0, sticky="ew", padx=10, pady=(8, 10))
        compose.grid_columnconfigure(0, weight=1)

        self.message_entry = ctk.CTkEntry(compose, placeholder_text="Message #general")
        self.message_entry.grid(row=0, column=0, padx=(10, 8), pady=10, sticky="ew")
        self.message_entry.bind("<Return>", lambda _e: self._send_message())
        self.message_entry.bind("<KeyRelease>", self._send_typing)

        ctk.CTkButton(compose, text="Send", width=90, command=self._send_message).grid(
            row=0, column=1, padx=(0, 10), pady=10
        )

        self.users_pane = ctk.CTkFrame(self.app_view, width=270)
        self.users_pane.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)
        self.users_pane.grid_propagate(False)
        self.users_pane.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.users_pane, text="Members", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        self.users_listbox = tk.Listbox(
            self.users_pane,
            bg="#1f2937",
            fg="#e5e7eb",
            selectbackground="#2563eb",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        self.users_listbox.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.users_listbox.bind("<<ListboxSelect>>", self._on_user_select)

        actions = ctk.CTkFrame(self.users_pane, fg_color="transparent")
        actions.grid(row=2, column=0, padx=12, pady=(6, 12), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)

        for row, (label, callback) in enumerate(
            [
                ("DM User", self._dm_user),
                ("DM History", self._dm_history),
                ("Change Username", self._change_username),
                ("Set Role", self._set_role),
            ]
        ):
            ctk.CTkButton(actions, text=label, command=callback).grid(row=row, column=0, pady=4, sticky="ew")

        self._set_app_visible(False)

    def _set_app_visible(self, is_visible: bool) -> None:
        if is_visible:
            self.auth_view.grid_remove()
            self.app_view.grid()
        else:
            self.app_view.grid_remove()
            self.auth_view.grid()

    def _save_connection_settings(self) -> None:
        ws_url = self.ws_url_entry.get().strip()
        if not ws_url:
            self.auth_status.configure(text="WebSocket URL is required")
            return

        try:
            reconnect_delay = float(self.reconnect_delay_entry.get().strip())
            reconnect_delay = max(0.5, min(10.0, reconnect_delay))
        except ValueError:
            self.auth_status.configure(text="Reconnect delay must be a number")
            return

        self.settings.ws_url = ws_url
        self.settings.reconnect_delay = reconnect_delay
        self._save_settings()
        self.auth_status.configure(text="Connection settings saved", text_color="#8bf5b2")

    def _submit_auth(self) -> None:
        username = self.username_entry.get().strip().lower()
        password = self.password_entry.get()

        if not username or not password:
            self.auth_status.configure(text="Username and password are required", text_color="#ff8a9c")
            return

        mode = self.auth_mode.get()
        self.auth_status.configure(text="", text_color="#ff8a9c")

        self._send(
            {
                "type": "auth",
                "action": mode,
                "username": username,
                "password": password,
            }
        )

    def _connect(self) -> None:
        self.stop_event.clear()
        ws_url = self.settings.ws_url

        def on_open(_ws: websocket.WebSocketApp) -> None:
            self.events.put(("status", "Connected"))

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            try:
                packet = json.loads(message)
            except json.JSONDecodeError:
                self.events.put(("system", "Received invalid packet"))
                return
            self.events.put(("packet", packet))

        def on_error(_ws: websocket.WebSocketApp, error: Any) -> None:
            self.events.put(("status", f"Connection error: {error}"))

        def on_close(_ws: websocket.WebSocketApp, _code: Any, _reason: Any) -> None:
            self.events.put(("status", "Disconnected"))
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

    def _schedule_reconnect(self) -> None:
        with self.reconnect_lock:
            if self.reconnect_scheduled:
                return
            self.reconnect_scheduled = True

        def reconnect_worker() -> None:
            time.sleep(self.settings.reconnect_delay)
            if not self.stop_event.is_set():
                self.events.put(("reconnect", None))
            with self.reconnect_lock:
                self.reconnect_scheduled = False

        threading.Thread(target=reconnect_worker, daemon=True).start()

    def _manual_reconnect(self) -> None:
        self.stop_event.set()
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception:
                pass

        self.stop_event.clear()
        self._connect()

    def _send(self, packet: dict[str, Any]) -> None:
        if not self.ws_app or not self.ws_app.sock or not self.ws_app.sock.connected:
            self._append_system("Not connected to server")
            return

        try:
            self.ws_app.send(json.dumps(packet))
        except Exception as exc:
            self._append_system(f"Send failed: {exc}")

    def _pump_events(self) -> None:
        while not self.events.empty():
            kind, payload = self.events.get()
            if kind == "status":
                self.connection_state_label.configure(text=str(payload))
            elif kind == "system":
                self._append_system(str(payload))
            elif kind == "packet":
                self._handle_packet(payload)
            elif kind == "reconnect":
                self._connect()

        self.after(120, self._pump_events)

    def _handle_packet(self, packet: dict[str, Any]) -> None:
        packet_type = packet.get("type", "")

        if packet_type == "auth_ok":
            self.username = packet.get("username", self.username)
            self.role = packet.get("role", "member")
            self.role_badge.configure(text=self.role)
            self.is_authed = True
            self._set_app_visible(True)
            self._append_system(f"Logged in as {self.username}")
            self._send({"type": "who"})
            return

        if packet_type == "auth_error":
            self.auth_status.configure(text=packet.get("message", "Authentication failed"), text_color="#ff8a9c")
            return

        if packet_type in ("welcome", "channel_switched"):
            self.current_channel = packet.get("channel", "general")
            self.channels = packet.get("channels", ["general"])
            self.channel_title_label.configure(text=f"#{self.current_channel}")
            self.message_entry.configure(placeholder_text=f"Message #{self.current_channel}")
            self._render_channels()
            self._render_history(packet.get("history", []))
            return

        if packet_type == "user_list":
            self.users = packet.get("users", [])
            self._render_users()
            return

        if packet_type == "message":
            author = packet.get("author", "?")
            content = packet.get("content", "")
            self._append_message(author, content)
            return

        if packet_type == "typing":
            user = packet.get("username", "")
            channel = packet.get("channel", "")
            if user and user != self.username and channel == self.current_channel:
                self.typing_label.configure(text=f"{user} is typing...")
                self.after(2000, lambda: self.typing_label.configure(text=""))
            return

        if packet_type == "dm":
            sender = packet.get("sender", "")
            recipient = packet.get("recipient", "")
            peer = recipient if sender == self.username else sender
            self._append_system(f"DM with {peer}: {packet.get('content', '')}")
            return

        if packet_type == "dm_history":
            with_user = packet.get("with", "?")
            self._append_system(f"--- DM history with {with_user} ---")
            for item in packet.get("history", []):
                sender = item.get("sender", "?")
                content = item.get("content", "")
                self._append_system(f"{sender}: {content}")
            return

        if packet_type == "role_update":
            self.role = packet.get("role", self.role)
            self.role_badge.configure(text=self.role)
            self._append_system(f"Role updated to {self.role}")
            return

        if packet_type == "username_changed":
            self.username = packet.get("username", self.username)
            self._append_system(f"Username changed to {self.username}")
            return

        if packet_type in ("action_error", "system"):
            self._append_system(packet.get("message", "Action failed"))
            return

    def _render_history(self, history: list[dict[str, Any]]) -> None:
        self.messages_text.configure(state="normal")
        self.messages_text.delete("1.0", "end")
        self.messages_text.configure(state="disabled")

        for item in history:
            deleted = bool(item.get("deleted"))
            author = item.get("author", "?")
            content = "[deleted]" if deleted else item.get("content", "")
            self._append_message(author, content)

    def _append_message(self, author: str, content: str) -> None:
        line = f"{author}: {content}"
        self.messages_text.configure(state="normal")
        self.messages_text.insert("end", line + "\n")
        self.messages_text.see("end")
        self.messages_text.configure(state="disabled")

    def _append_system(self, text: str) -> None:
        self._append_message("System", text)

    def _render_channels(self) -> None:
        self.channels_listbox.delete(0, "end")
        for channel in self.channels:
            self.channels_listbox.insert("end", f"#{channel}")

        for idx, channel in enumerate(self.channels):
            if channel == self.current_channel:
                self.channels_listbox.selection_set(idx)
                break

    def _render_users(self) -> None:
        self.users_listbox.delete(0, "end")
        for user in self.users:
            self.users_listbox.insert("end", user)

    def _on_channel_select(self, _event: Any) -> None:
        selection = self.channels_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.channels):
            return
        chosen = self.channels[idx]
        if chosen != self.current_channel:
            self._send({"type": "switch_channel", "channel": chosen})

    def _on_user_select(self, _event: Any) -> None:
        selection = self.users_listbox.curselection()
        if not selection:
            self.selected_user = ""
            return
        idx = selection[0]
        if idx < len(self.users):
            self.selected_user = self.users[idx]

    def _new_channel(self) -> None:
        name = simpledialog.askstring("New Channel", "Channel name:", parent=self)
        if not name:
            return
        channel = name.strip().lower().replace(" ", "-")
        if not channel:
            return
        self._send({"type": "switch_channel", "channel": channel})

    def _send_message(self) -> None:
        if not self.is_authed:
            self._append_system("Authenticate first")
            return

        content = self.message_entry.get().strip()
        if not content:
            return

        self._send({"type": "message", "content": content})
        self.message_entry.delete(0, "end")

    def _send_typing(self, _event: Any) -> None:
        if self.is_authed:
            self._send({"type": "typing"})

    def _require_selected_user(self) -> str | None:
        if not self.selected_user:
            messagebox.showinfo("PyChatter", "Select a user first")
            return None
        return self.selected_user

    def _dm_user(self) -> None:
        target = self._require_selected_user()
        if not target:
            return
        text = simpledialog.askstring("Direct Message", f"Send to {target}:", parent=self)
        if not text:
            return
        self._send({"type": "dm", "to": target.lower(), "content": text.strip()})

    def _dm_history(self) -> None:
        target = self._require_selected_user()
        if not target:
            return
        self._send({"type": "dm_history", "with": target.lower()})

    def _change_username(self) -> None:
        new_name = simpledialog.askstring("Change Username", "New username:", parent=self)
        if not new_name:
            return
        normalized = new_name.strip().lower()
        if not normalized:
            return
        self._send({"type": "change_username", "new_username": normalized})

    def _set_role(self) -> None:
        if self.role != "admin":
            messagebox.showinfo("PyChatter", "Only admins can set roles")
            return

        target = self._require_selected_user()
        if not target:
            return

        role = simpledialog.askstring("Set Role", "Role: member | mod | admin", parent=self)
        if not role:
            return
        normalized = role.strip().lower()
        if normalized not in {"member", "mod", "admin"}:
            messagebox.showerror("PyChatter", "Invalid role")
            return

        self._send({"type": "promote", "username": target.lower(), "role": normalized})

    def _on_close(self) -> None:
        self.stop_event.set()
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = PyChatterClient()
    app.mainloop()
