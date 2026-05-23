from __future__ import annotations

import json
import os
import queue
import socket
import select
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from crypto_utils import EncryptedPacket, decrypt_json, derive_session_key, encrypt_json
from models import ChatRoom, Message
from protocol import ConnState, json_dumps, json_loads, send_frame, try_extract_frames
from storage import Storage, init_db


def _now_ms() -> int:
    return int(time.time() * 1000)


def _load_config() -> dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        v = json.load(f)
    if not isinstance(v, dict):
        raise ValueError("config.json must be an object")
    return v


def _sanitize_filename(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)[:64] or "room"


class Server:
    def __init__(self, host: str, port: int, shared_secret: str, db_path: str, log_dir: str, export_dir: str) -> None:
        self._host = host
        self._port = port
        self._shared_secret = shared_secret
        self._storage = Storage(db_path)
        self._log_dir = Path(log_dir)
        self._export_dir = Path(export_dir)

        self._state_lock = threading.Lock()
        self._conns: dict[socket.socket, ConnState] = {}
        self._users: dict[str, socket.socket] = {}
        self._rooms: dict[str, ChatRoom] = {}

        self._msg_persist_q: queue.Queue[Message] = queue.Queue()
        self._stop_evt = threading.Event()

        self._send_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=8)

    def run(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._export_dir.mkdir(parents=True, exist_ok=True)

        t = threading.Thread(target=self._persist_worker, daemon=True)
        t.start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self._host, self._port))
            listener.listen()
            print(f"Server listening on {self._host}:{self._port}")

            while not self._stop_evt.is_set():
                read_socks = [listener]
                with self._state_lock:
                    read_socks.extend(self._conns.keys())
                r, _, _ = select.select(read_socks, [], [], 0.5)
                for s in r:
                    if s is listener:
                        self._accept(listener)
                    else:
                        self._recv(s)

    def _accept(self, listener: socket.socket) -> None:
        client, addr = listener.accept()
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        st = ConnState(sock=client, addr=(str(addr[0]), int(addr[1])))
        with self._state_lock:
            self._conns[client] = st
        print(f"Client connected: {st.addr[0]}:{st.addr[1]}")

    def _recv(self, s: socket.socket) -> None:
        st = self._conns.get(s)
        if st is None:
            return
        try:
            data = s.recv(65536)
        except OSError:
            self._disconnect(s)
            return
        if not data:
            self._disconnect(s)
            return
        st.buffer.extend(data)
        try:
            frames = try_extract_frames(st.buffer)
        except Exception:
            self._disconnect(s)
            return
        for payload in frames:
            self._pool.submit(self._handle_frame, st, payload)

    def _disconnect(self, s: socket.socket) -> None:
        with self._state_lock:
            st = self._conns.pop(s, None)
        if st is None:
            return
        try:
            s.close()
        except OSError:
            pass
        username = st.username
        room = st.room
        if username:
            with self._state_lock:
                if self._users.get(username) is s:
                    del self._users[username]
                if room and room in self._rooms:
                    self._rooms[room].leave(username)
                    members = set(self._rooms[room].members)
            if room:
                self._broadcast_event(
                    room,
                    {"type": "user_left", "room": room, "username": username, "ts_ms": _now_ms()},
                    members=members,
                )
        print(f"Client disconnected: {st.addr[0]}:{st.addr[1]}")

    def _send_plain(self, st: ConnState, obj: dict[str, Any]) -> None:
        payload = json_dumps(obj)
        with self._send_lock:
            send_frame(st.sock, payload)

    def _send_encrypted(self, st: ConnState, obj: dict[str, Any]) -> None:
        if st.session_key is None:
            raise RuntimeError("session key not established")
        payload = json_dumps(obj)
        pkt = encrypt_json(st.session_key, payload)
        with self._send_lock:
            send_frame(st.sock, pkt.to_bytes())

    def _handle_frame(self, st: ConnState, payload: bytes) -> None:
        try:
            if st.session_key is None:
                self._handle_handshake(st, payload)
                return
            pkt = EncryptedPacket.from_bytes(payload)
            plaintext = decrypt_json(st.session_key, pkt)
            req = json_loads(plaintext)
            self._handle_request(st, req)
        except Exception:
            try:
                self._send_plain(st, {"type": "error", "message": "bad request"})
            except Exception:
                pass

    def _handle_handshake(self, st: ConnState, payload: bytes) -> None:
        req = json_loads(payload)
        if req.get("type") != "handshake":
            raise ValueError("missing handshake")
        salt_b64 = req.get("salt")
        if not isinstance(salt_b64, str):
            raise ValueError("bad salt")
        salt = os.urandom(16)
        try:
            import base64

            salt = base64.b64decode(salt_b64.encode("ascii"))
        except Exception:
            raise ValueError("bad salt")
        if len(salt) < 8 or len(salt) > 64:
            raise ValueError("bad salt length")
        st.session_key = derive_session_key(self._shared_secret, salt)
        self._send_plain(st, {"type": "handshake_ok"})

    def _handle_request(self, st: ConnState, req: dict[str, Any]) -> None:
        t = req.get("type")
        if t == "register":
            self._cmd_register(st, req)
        elif t == "login":
            self._cmd_login(st, req)
        elif t == "join":
            self._cmd_join(st, req)
        elif t == "chat":
            self._cmd_chat(st, req)
        elif t == "list_rooms":
            self._cmd_list_rooms(st)
        elif t == "list_users":
            self._cmd_list_users(st)
        elif t == "export":
            self._cmd_export(st, req)
        else:
            self._send_encrypted(st, {"type": "error", "message": "unknown command"})

    def _cmd_register(self, st: ConnState, req: dict[str, Any]) -> None:
        username = req.get("username")
        password = req.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self._send_encrypted(st, {"type": "error", "message": "bad username/password"})
            return
        if len(username) < 3 or len(username) > 20:
            self._send_encrypted(st, {"type": "error", "message": "username length 3-20"})
            return
        if self._storage.user_exists(username):
            self._send_encrypted(st, {"type": "error", "message": "user exists"})
            return
        try:
            self._storage.register_user(username, password, _now_ms())
        except Exception:
            self._send_encrypted(st, {"type": "error", "message": "register failed"})
            return
        self._send_encrypted(st, {"type": "ok", "message": "registered"})

    def _cmd_login(self, st: ConnState, req: dict[str, Any]) -> None:
        username = req.get("username")
        password = req.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self._send_encrypted(st, {"type": "error", "message": "bad username/password"})
            return
        if not self._storage.verify_user(username, password):
            self._send_encrypted(st, {"type": "error", "message": "invalid credentials"})
            return
        with self._state_lock:
            if username in self._users and self._users[username] is not st.sock:
                self._send_encrypted(st, {"type": "error", "message": "user already online"})
                return
            st.username = username
            self._users[username] = st.sock
        self._send_encrypted(st, {"type": "ok", "message": "logged in", "username": username})

    def _cmd_join(self, st: ConnState, req: dict[str, Any]) -> None:
        room = req.get("room")
        if st.username is None:
            self._send_encrypted(st, {"type": "error", "message": "login required"})
            return
        if not isinstance(room, str) or not room:
            self._send_encrypted(st, {"type": "error", "message": "bad room"})
            return
        with self._state_lock:
            if room not in self._rooms:
                self._rooms[room] = ChatRoom(name=room)
            self._rooms[room].join(st.username)
            st.room = room
            members = set(self._rooms[room].members)
        self._send_encrypted(st, {"type": "ok", "message": "joined", "room": room})
        self._broadcast_event(
            room,
            {"type": "user_joined", "room": room, "username": st.username, "ts_ms": _now_ms()},
            members=members,
        )

    def _cmd_chat(self, st: ConnState, req: dict[str, Any]) -> None:
        if st.username is None:
            self._send_encrypted(st, {"type": "error", "message": "login required"})
            return
        room = st.room
        if not room:
            self._send_encrypted(st, {"type": "error", "message": "join a room first"})
            return
        body = req.get("body")
        mentions = req.get("mentions", [])
        if not isinstance(body, str) or not body:
            self._send_encrypted(st, {"type": "error", "message": "empty message"})
            return
        if not isinstance(mentions, list) or any(not isinstance(x, str) for x in mentions):
            mentions = []
        ts = _now_ms()
        msg = Message(room=room, sender=st.username, body=body, ts_ms=ts, mentions=list(mentions))
        with self._state_lock:
            members = set(self._rooms.get(room, ChatRoom(room)).members)
        self._broadcast_event(
            room,
            {
                "type": "room_message",
                "room": room,
                "sender": st.username,
                "body": body,
                "mentions": msg.mentions,
                "ts_ms": ts,
            },
            members=members,
        )
        self._msg_persist_q.put(msg)
        self._send_encrypted(st, {"type": "ok"})

    def _cmd_list_rooms(self, st: ConnState) -> None:
        with self._state_lock:
            rooms = [{"name": r.name, "members": len(r.members)} for r in self._rooms.values()]
        self._send_encrypted(st, {"type": "rooms", "rooms": rooms})

    def _cmd_list_users(self, st: ConnState) -> None:
        with self._state_lock:
            users = sorted(self._users.keys())
        self._send_encrypted(st, {"type": "users", "users": users})

    def _cmd_export(self, st: ConnState, req: dict[str, Any]) -> None:
        room = req.get("room")
        if not isinstance(room, str) or not room:
            self._send_encrypted(st, {"type": "error", "message": "bad room"})
            return
        rows = self._storage.export_room(room)
        ts = _now_ms()
        fname = f"{_sanitize_filename(room)}_{ts}.txt"
        path = self._export_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            for _id, sender, body, ts_ms in rows:
                f.write(f"{ts_ms}\t{sender}\t{body}\n")
        self._send_encrypted(st, {"type": "export_ready", "room": room, "path": str(path)})

    def _broadcast_event(self, room: str, event: dict[str, Any], *, members: set[str]) -> None:
        with self._state_lock:
            targets = [self._users.get(u) for u in members]
            conns = [self._conns.get(s) for s in targets if s is not None]
        for c in conns:
            if c is None or c.session_key is None:
                continue
            try:
                self._send_encrypted(c, event)
            except Exception:
                pass

    def _persist_worker(self) -> None:
        while not self._stop_evt.is_set():
            try:
                msg = self._msg_persist_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._storage.save_message(msg.room, msg.sender, msg.body, msg.ts_ms)
            except Exception:
                pass
            try:
                log_path = self._log_dir / f"{_sanitize_filename(msg.room)}.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{msg.ts_ms}\t{msg.sender}\t{msg.body}\n")
            except Exception:
                pass


def main() -> None:
    cfg = _load_config()
    host = str(cfg.get("host", "127.0.0.1"))
    port = int(cfg.get("port", 5050))
    shared_secret = str(cfg.get("shared_secret", ""))
    if not shared_secret or shared_secret == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET":
        raise RuntimeError("Please set a strong shared_secret in config.json")
    db_path = str(cfg.get("db_path", "data/chat.db"))
    log_dir = str(cfg.get("log_dir", "data/logs"))
    export_dir = str(cfg.get("export_dir", "data/exports"))
    init_db(db_path)
    Server(host, port, shared_secret, db_path, log_dir, export_dir).run()


if __name__ == "__main__":
    main()
