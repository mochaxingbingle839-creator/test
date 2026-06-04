from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Optional


def _load_config_db_path() -> Optional[str]:
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            v = json.load(f)
        if isinstance(v, dict) and isinstance(v.get("db_path"), str) and v["db_path"]:
            return v["db_path"]
    except Exception:
        return None
    return None


def _open_db(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    return sqlite3.connect(db_path)


def _print_rows(rows: list[tuple[Any, ...]]) -> None:
    for r in rows:
        sys.stdout.write("\t".join([str(x) for x in r]) + "\n")


def main() -> int:
    default_db = _load_config_db_path() or os.path.join("data", "chat.db")

    p = argparse.ArgumentParser(prog="inspect_db.py")
    p.add_argument("--db", default=default_db, help="SQLite db path (default: from config.json or data/chat.db)")
    p.add_argument("--users", action="store_true", help="List users")
    p.add_argument("--rooms", action="store_true", help="List rooms (distinct room names)")
    p.add_argument("--messages", nargs="?", const="__ALL__", help="List messages (optional room name)")
    p.add_argument("--limit", type=int, default=50, help="Max rows to print for messages")
    args = p.parse_args()

    if not (args.users or args.rooms or args.messages is not None):
        p.print_help()
        return 2

    try:
        conn = _open_db(args.db)
    except FileNotFoundError:
        sys.stderr.write(f"DB not found: {args.db}\n")
        sys.stderr.write("Start server once and register/login/send a message so the DB is created.\n")
        return 1

    try:
        if args.users:
            rows = conn.execute("SELECT username, created_at_ms FROM users ORDER BY created_at_ms ASC").fetchall()
            _print_rows(rows)

        if args.rooms:
            rows = conn.execute("SELECT DISTINCT room FROM messages ORDER BY room ASC").fetchall()
            _print_rows(rows)

        if args.messages is not None:
            room = None if args.messages == "__ALL__" else args.messages
            if room:
                rows = conn.execute(
                    "SELECT room, sender, body, ts_ms FROM messages WHERE room = ? ORDER BY ts_ms DESC LIMIT ?",
                    (room, args.limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT room, sender, body, ts_ms FROM messages ORDER BY ts_ms DESC LIMIT ?",
                    (args.limit,),
                ).fetchall()
            _print_rows(rows)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

