from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass(frozen=True)
class User:
    username: str


@dataclass
class Message:
    room: str
    sender: str
    body: str
    ts_ms: int
    mentions: list[str] = field(default_factory=list)


@dataclass
class ChatRoom:
    name: str
    members: Set[str] = field(default_factory=set)

    def join(self, username: str) -> None:
        self.members.add(username)

    def leave(self, username: str) -> None:
        self.members.discard(username)

    def has(self, username: str) -> bool:
        return username in self.members

