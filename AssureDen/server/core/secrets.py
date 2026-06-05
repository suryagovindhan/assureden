"""
server/core/secrets.py — Pluggable Secret Provider
────────────────────────────────────────────────────
M1: FernetSecretProvider — local key in .env / environment variable
Future: AzureKeyVaultProvider, HashiCorpVaultProvider (same interface)

Key stored in ASSUREDEN_SECRET_KEY env var (base64url Fernet key).
Generate a new key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from abc import ABC, abstractmethod

try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False


_MASK = "***MASKED***"

# ─────────────────────────────────────────────────────────────────────────────
# Abstract Interface
# ─────────────────────────────────────────────────────────────────────────────

class SecretProvider(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> str: ...

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str: ...

    def mask(self, value: str) -> str:
        """Returns a masked representation safe for logs/screenshots."""
        return _MASK


# ─────────────────────────────────────────────────────────────────────────────
# Fernet Implementation (M1 default)
# ─────────────────────────────────────────────────────────────────────────────

class FernetSecretProvider(SecretProvider):
    def __init__(self):
        if not _FERNET_AVAILABLE:
            raise RuntimeError(
                "cryptography package not installed. Run: pip install cryptography"
            )
        raw_key = os.getenv("ASSUREDEN_SECRET_KEY")
        if not raw_key:
            # Auto-generate for dev — in production, always set the env var
            generated = Fernet.generate_key()
            os.environ["ASSUREDEN_SECRET_KEY"] = generated.decode()
            print(
                f"[WARN] ASSUREDEN_SECRET_KEY not set. Generated ephemeral key for this session. "
                f"Set it permanently in your .env file:\n  ASSUREDEN_SECRET_KEY={generated.decode()}"
            )
            self._fernet = Fernet(generated)
        else:
            self._fernet = Fernet(raw_key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("Failed to decrypt secret — key mismatch or corrupted data.")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_provider: SecretProvider | None = None


def get_secret_provider() -> SecretProvider:
    """Returns the active SecretProvider singleton (lazy init)."""
    global _provider
    if _provider is None:
        _provider = FernetSecretProvider()
    return _provider
