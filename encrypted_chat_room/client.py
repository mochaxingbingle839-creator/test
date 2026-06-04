from __future__ import annotations

import base64
import json
import os
import queue
import re
import socket
import threading
import time
from typing import Any, Optional

from crypto_utils import EncryptedPacket, decrypt_json, derive_session_key, encrypt_json
from protocol import json_dumps, json_loads, send_frame, try_extract_frames


def _load_config() -> dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        v = json.load(f)
    if not isinstance(v, dict):
        raise ValueError("config.json must be an object")
    return v


def _apply_text_features(text: str) -> tuple[str, list[str]]:
    emoticons = {
        ":)": "😊",
        ":-)": "😊",
        ":(": "🙁",
        ":-(": "🙁",
        ";)": "😉",
        ";-)": "😉",
    }
    for k, v in emoticons.items():
        text = text.replace(k, v)
    mentions = re.findall(r"@([A-Za-z0-9_]{3,20})", text)
    return text, mentions


def _highlight_mentions(text: str, *, me: Optional[str] = None) -> str:
    """
    在终端输出里高亮 @提及（ANSI 颜色）。
    - 默认：青色高亮所有 @xxx
    - 如果提及到当前用户 me：使用更醒目的黄色背景
    注：需要终端支持 ANSI 转义序列（Windows Terminal / VS Code 终端一般都支持）。
    """

    def _repl(m: re.Match[str]) -> str:
        username = m.group(1)
        whole = m.group(0)  # 形如 "@alice"
        # 提及自己：黑字黄底
        if me and username == me:
            return f"\x1b[30;43m{whole}\x1b[0m"
        # 提及他人：青色
        return f"\x1b[36m{whole}\x1b[0m"

    return re.sub(r"@([A-Za-z0-9_]{3,20})", _repl, text)


class Client:
    def __init__(self, host: str, port: int, shared_secret: str) -> None:
        self._host = host
        self._port = port
        self._shared_secret = shared_secret
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._recv_buf = bytearray()
        self._session_key: Optional[bytes] = None
        self._out_q: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._stop_evt = threading.Event()
        self._username: Optional[str] = None
        self._room: Optional[str] = None

    def run(self) -> None:
        self._sock.connect((self._host, self._port))
        self._handshake()

        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

        print("Commands: /register u p | /login u p | /join room | /rooms | /users | /export room | /quit")
        while not self._stop_evt.is_set():
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.startswith("/"):
                if self._handle_command(line):
                    break
            else:
                self._send_chat(line)

        self._stop_evt.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def _handshake(self) -> None:
        salt = os.urandom(16)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        send_frame(self._sock, json_dumps({"type": "handshake", "salt": salt_b64}))
        ok = self._recv_one_plain()
        if ok.get("type") != "handshake_ok":
            raise RuntimeError("handshake failed")
        self._session_key = derive_session_key(self._shared_secret, salt)

    def _recv_one_plain(self) -> dict[str, Any]:
        while True:
            data = self._sock.recv(65536)
            if not data:
                raise RuntimeError("disconnected")
            self._recv_buf.extend(data)
            frames = try_extract_frames(self._recv_buf)
            if frames:
                return json_loads(frames[0])

    def _send_encrypted(self, obj: dict[str, Any]) -> None:
        if self._session_key is None:
            raise RuntimeError("session key not established")
        pkt = encrypt_json(self._session_key, json_dumps(obj))
        send_frame(self._sock, pkt.to_bytes())

    def _handle_command(self, line: str) -> bool:
        parts = line.split()
        cmd = parts[0].lower()
        if cmd == "/quit":
            return True
        if cmd == "/register" and len(parts) >= 3:
            self._send_encrypted({"type": "register", "username": parts[1], "password": parts[2]})
            return False
        if cmd == "/login" and len(parts) >= 3:
            self._send_encrypted({"type": "login", "username": parts[1], "password": parts[2]})
            return False
        if cmd == "/join" and len(parts) >= 2:
            self._room = parts[1]
            self._send_encrypted({"type": "join", "room": parts[1]})
            return False
        if cmd == "/rooms":
            self._send_encrypted({"type": "list_rooms"})
            return False
        if cmd == "/users":
            self._send_encrypted({"type": "list_users"})
            return False
        if cmd == "/export" and len(parts) >= 2:
            self._send_encrypted({"type": "export", "room": parts[1]})
            return False
        print("Unknown command")
        return False

    def _send_chat(self, text: str) -> None:
        if not self._room:
            print("Join a room first: /join <room>")
            return
        body, mentions = _apply_text_features(text)
        self._send_encrypted({"type": "chat", "body": body, "mentions": mentions})

    def _recv_loop(self) -> None:
        try:
            while not self._stop_evt.is_set():
                data = self._sock.recv(65536)
                if not data:
                    print("Disconnected")
                    self._stop_evt.set()
                    return
                self._recv_buf.extend(data)
                frames = try_extract_frames(self._recv_buf)
                for payload in frames:
                    self._handle_payload(payload)
        except OSError:
            self._stop_evt.set()

    def _handle_payload(self, payload: bytes) -> None:
        if self._session_key is None:
            return
        try:
            pkt = EncryptedPacket.from_bytes(payload)
            plaintext = decrypt_json(self._session_key, pkt)
            msg = json_loads(plaintext)
        except Exception:
            return
        t = msg.get("type")
        if t == "ok":
            if "username" in msg:
                self._username = str(msg.get("username"))
            if msg.get("message"):
                print(str(msg.get("message")))
            return
        if t == "error":
            print(f"Error: {msg.get('message')}")
            return
        if t == "rooms":
            rooms = msg.get("rooms", [])
            if isinstance(rooms, list):
                for r in rooms:
                    if isinstance(r, dict):
                        print(f"{r.get('name')} ({r.get('members')} users)")
            return
        if t == "users":
            users = msg.get("users", [])
            if isinstance(users, list):
                print("Online:", ", ".join([str(u) for u in users]))
            return
        if t == "room_message":
            room = msg.get("room")
            sender = msg.get("sender")
            body = msg.get("body")
            ts = msg.get("ts_ms")
            mentions = msg.get("mentions", [])
            if (
                self._username
                and isinstance(mentions, list)
                and any(isinstance(x, str) and x == self._username for x in mentions)
            ):
                print(f"[{room}] 提示：你被 @{self._username} 提及（来自 {sender}）")
            # 终端“富文本”展示：高亮 @提及
            body_rich = _highlight_mentions(str(body), me=self._username)
            print(f"[{room}] {ts} {sender}: {body_rich}")
            return
        if t == "user_joined":
            print(f"[{msg.get('room')}] {msg.get('username')} joined")
            return
        if t == "user_left":
            print(f"[{msg.get('room')}] {msg.get('username')} left")
            return
        if t == "export_ready":
            print(f"Exported {msg.get('room')} to {msg.get('path')}")
            return


def main() -> None:
    cfg = _load_config()
    host = str(cfg.get("host", "127.0.0.1"))
    port = int(cfg.get("port", 5050))
    shared_secret = str(cfg.get("shared_secret", ""))
    if not shared_secret or shared_secret == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET":
        raise RuntimeError("Please set a strong shared_secret in config.json")
    Client(host, port, shared_secret).run()


if __name__ == "__main__":
    main()
