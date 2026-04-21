"""Cryptography utilities for encrypting sensitive data like private keys."""

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import settings


class EncryptedString:
    """Wrapper for encrypted string storage."""

    def __init__(self, encrypted: Optional[str] = None):
        self.encrypted = encrypted

    def __repr__(self) -> str:
        if self.encrypted and len(self.encrypted) > 10:
            return f"EncryptedString('{self.encrypted[:10]}...')"
        return "EncryptedString('')"

    def __str__(self) -> str:
        return self.encrypted or ""

    def __bool__(self) -> bool:
        return bool(self.encrypted)


def _get_fernet() -> Fernet:
    """Get Fernet cipher using JWT_SECRET as key."""
    # Derive a 32-byte key from JWT_SECRET using SHA256
    key = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    # Encode to base64 for Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_private_key(private_key: str) -> str:
    """Encrypt a private key for storage.

    Args:
        private_key: The plaintext private key to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    if not private_key:
        return ""

    fernet = _get_fernet()
    encrypted = fernet.encrypt(private_key.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_private_key(encrypted_key: str) -> Optional[str]:
    """Decrypt an encrypted private key.

    Args:
        encrypted_key: Base64-encoded encrypted string

    Returns:
        Dec plaintext private key or None if decryption fails
    """
    if not encrypted_key:
        return None

    try:
        fernet = _get_fernet()
        decoded = base64.b64decode(encrypted_key.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    except Exception:
        return None


def generate_encryption_key() -> str:
    """Generate a new random encryption key (for initial setup)."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()