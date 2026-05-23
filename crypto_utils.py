from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def derive_session_key(shared_secret: str, salt: bytes, iterations: int = 200_000) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(shared_secret.encode("utf-8"))


@dataclass(frozen=True)
class EncryptedPacket:
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        return self.nonce + self.ciphertext

    @staticmethod
    def from_bytes(b: bytes) -> "EncryptedPacket":
        if len(b) < 12:
            raise ValueError("packet too short")
        return EncryptedPacket(nonce=b[:12], ciphertext=b[12:])


def encrypt_json(key: bytes, plaintext: bytes) -> EncryptedPacket:
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext, None)
    return EncryptedPacket(nonce=nonce, ciphertext=ct)


def decrypt_json(key: bytes, packet: EncryptedPacket) -> bytes:
    aes = AESGCM(key)
    return aes.decrypt(packet.nonce, packet.ciphertext, None)

