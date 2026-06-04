from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from hashlib import pbkdf2_hmac
from typing import Optional


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _db_connect(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str) -> None:
    conn = _db_connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              username TEXT PRIMARY KEY,
              salt BLOB NOT NULL,
              pw_hash BLOB NOT NULL,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              room TEXT NOT NULL,
              sender TEXT NOT NULL,
              body TEXT NOT NULL,
              ts_ms INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class PasswordHash:
    salt: bytes
    pw_hash: bytes


def hash_password(password: str, *, salt: Optional[bytes] = None, iterations: int = 200_000) -> PasswordHash:
    s = salt if salt is not None else os.urandom(16)
    h = pbkdf2_hmac("sha256", password.encode("utf-8"), s, iterations, dklen=32)
    return PasswordHash(salt=s, pw_hash=h)


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = _db_connect(self._db_path)
            self._local.conn = conn
        return conn

    def register_user(self, username: str, password: str, ts_ms: int) -> None:
        ph = hash_password(password)
        conn = self._conn()
        conn.execute(
            "INSERT INTO users(username, salt, pw_hash, created_at_ms) VALUES (?, ?, ?, ?)",
            (username, ph.salt, ph.pw_hash, ts_ms),
        )
        conn.commit()

    def verify_user(self, username: str, password: str) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT salt, pw_hash FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return False
        salt, pw_hash = row[0], row[1]
        ph = hash_password(password, salt=salt)
        return ph.pw_hash == pw_hash

    def user_exists(self, username: str) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        return row is not None

    def save_message(self, room: str, sender: str, body: str, ts_ms: int) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO messages(room, sender, body, ts_ms) VALUES (?, ?, ?, ?)",
            (room, sender, body, ts_ms),
        )
        conn.commit()

    def export_room(self, room: str) -> list[tuple[int, str, str, int]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, sender, body, ts_ms FROM messages WHERE room = ? ORDER BY ts_ms ASC",
            (room,),
        ).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in rows]

