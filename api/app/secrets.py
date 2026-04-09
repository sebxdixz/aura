from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(raw_key: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
        if len(decoded) == 32:
            return raw_key.encode("utf-8")
    except Exception:
        pass
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    key = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("SECRETS_ENCRYPTION_KEY is required for tenant integrations")
    derived = _derive_fernet_key(key)
    return Fernet(derived)


def encrypt_text(plain_text: str) -> str:
    fernet = _get_fernet()
    return fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    fernet = _get_fernet()
    try:
        return fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt tenant integration secret") from exc
