from __future__ import annotations
"""Encrypted storage helpers for integration secrets."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app import config


def _raw_key() -> str:
    return (config.INTEGRATION_SECRET_KEY or "").strip()


def _fernet() -> Fernet:
    raw = _raw_key()
    if not raw:
        raise RuntimeError("Falta INTEGRATION_SECRET_KEY para guardar secretos de integraciones.")
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError("El secreto no puede estar vacio.")
    return _fernet().encrypt(clean.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_value: str) -> str | None:
    try:
        return _fernet().decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, RuntimeError):
        return None

