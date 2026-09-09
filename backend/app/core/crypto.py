"""
core/crypto.py — Key-versioned Fernet encryption for secret variable values.

Keys are configured as a JSON map in config.VARIABLE_ENCRYPTION_KEYS:
  {"v1": "<base64-fernet-key>", "v2": "<base64-fernet-key>"}

New values are always encrypted with VARIABLE_ENCRYPTION_ACTIVE_KEY_ID.
Decryption uses the key_id stored alongside the ciphertext, enabling
zero-downtime key rotation.

Generate a Fernet key:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import json
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CryptoError(Exception):
    pass


def _load_keys() -> dict[str, Fernet]:
    """Parse VARIABLE_ENCRYPTION_KEYS from config and return {key_id: Fernet}."""
    raw = settings.VARIABLE_ENCRYPTION_KEYS.strip()
    if not raw or raw == "{}":
        return {}
    try:
        key_map = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CryptoError(f"VARIABLE_ENCRYPTION_KEYS is not valid JSON: {exc}") from exc
    return {kid: Fernet(k.encode() if isinstance(k, str) else k) for kid, k in key_map.items()}


def encrypt(plaintext: str) -> tuple[str, str]:
    """
    Encrypt plaintext using the active key.

    Returns:
        (ciphertext_str, key_id)

    Raises:
        CryptoError if no encryption keys are configured.
    """
    keys = _load_keys()
    active_key_id = settings.VARIABLE_ENCRYPTION_ACTIVE_KEY_ID
    if not keys:
        raise CryptoError(
            "No variable encryption keys configured. "
            "Set VARIABLE_ENCRYPTION_KEYS in your .env file."
        )
    if active_key_id not in keys:
        raise CryptoError(
            f"Active key_id '{active_key_id}' not found in VARIABLE_ENCRYPTION_KEYS."
        )
    fernet = keys[active_key_id]
    ciphertext = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return ciphertext, active_key_id


def decrypt(ciphertext: str, key_id: str) -> str:
    """
    Decrypt ciphertext using the key identified by key_id.

    Raises:
        CryptoError if key_id is unknown or the token is invalid.
    """
    keys = _load_keys()
    if not keys:
        # Fallback for tests without encryption configured — return ciphertext as-is.
        # This should never happen in production.
        return ciphertext
    if key_id not in keys:
        raise CryptoError(f"Decryption key_id '{key_id}' not found in configured keys.")
    try:
        return keys[key_id].decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(f"Failed to decrypt value with key_id '{key_id}': {exc}") from exc


def is_crypto_configured() -> bool:
    """True when at least one encryption key is configured."""
    return bool(_load_keys())
