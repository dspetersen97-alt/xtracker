"""Credential encryption for secure storage.

Uses Fernet symmetric encryption with a key derived from the app's SECRET_KEY.
Credentials are encrypted at rest in the database and can only be decrypted
by the running application instance that knows the SECRET_KEY.

Security model:
- Encryption key is derived from SECRET_KEY using PBKDF2 with a fixed salt
- If the database is stolen without the SECRET_KEY, credentials cannot be recovered
- The SECRET_KEY should be set via environment variable in production (not the default)
"""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app


# Fixed salt for key derivation. Not secret — just ensures the derived key
# is different from the raw SECRET_KEY even if they happen to be the same string.
_SALT = b"xtracker-credential-store-v1"


def _get_fernet():
    """Get a Fernet instance using the app's SECRET_KEY."""
    secret = current_app.config["SECRET_KEY"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)


def encrypt(plaintext):
    """Encrypt a string. Returns base64-encoded ciphertext string."""
    if not plaintext:
        return None
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext):
    """Decrypt a base64-encoded ciphertext string. Returns plaintext string.
    Returns None if decryption fails (wrong key, corrupted data).
    """
    if not ciphertext:
        return None
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None
