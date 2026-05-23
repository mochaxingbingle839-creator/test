from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass, field
from typing import Optional


def pack_frame(payload: bytes) -> bytes:
    return struct.pack("!I", len(payload)) + payload


def try_extract_frames(buffer: bytearray) -> list[bytes]:
    frames: list[bytes] = []
    while True:
        if len(buffer) < 4:
            return frames
        (n,) = struct.unpack("!I", buffer[:4])
        if n < 0 or n > 10_000_000:
            raise ValueError("invalid frame length")
        if len(buffer) < 4 + n:
            return frames
        payload = bytes(buffer[4 : 4 + n])
        del buffer[: 4 + n]
        frames.append(payload)
    return frames


def send_frame(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(pack_frame(payload))


def json_dumps(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_loads(b: bytes) -> dict:
    v = json.loads(b.decode("utf-8"))
    if not isinstance(v, dict):
        raise ValueError("json must be object")
    return v


@dataclass
class ConnState:
    sock: socket.socket
    addr: tuple[str, int]
    buffer: bytearray = field(default_factory=bytearray)
    session_key: Optional[bytes] = None
    username: Optional[str] = None
    room: Optional[str] = None
