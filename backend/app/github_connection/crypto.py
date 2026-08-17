"""
Symmetric token encryption using Fernet (AES-128-CBC + HMAC-SHA256).

The key lives in env var NEXTGENQA_CRYPTO_KEY. Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If the env var is missing we generate an *ephemeral* key on first import and
log a loud warning. This keeps dev environments working without setup but
means tokens are unreadable after a backend restart — which is the right
failure mode (better than silently storing plaintext or refusing to boot).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENV_VAR = "NEXTGENQA_CRYPTO_KEY"


def _load_fernet() -> Fernet:
    raw = os.getenv(_ENV_VAR, "").strip()
    if not raw:
        ephemeral = Fernet.generate_key()
        logger.warning(
            "%s not set — generated an ephemeral encryption key. Tokens "
            "saved this session will be unreadable after the backend "
            "restarts. Set %s in backend/.env to persist credentials.",
            _ENV_VAR, _ENV_VAR,
        )
        return Fernet(ephemeral)
    try:
        return Fernet(raw.encode())
    except Exception as e:
        raise RuntimeError(
            f"{_ENV_VAR} is not a valid Fernet key (must be 32 url-safe "
            f"base64-encoded bytes). Regenerate with `python -c "
            f"\"from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())\"`. Inner error: {e}"
        )


# Module-level singleton so we don't construct it per request.
_fernet: Optional[Fernet] = None


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = _load_fernet()
    return _fernet


def encrypt_token(plain: str) -> str:
    """Return the Fernet ciphertext as a UTF-8 string (safe to store in TEXT)."""
    return _f().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_token(cipher: str) -> str:
    """Reverse of encrypt_token. Raises InvalidToken on tamper / wrong key."""
    try:
        return _f().decrypt(cipher.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError(
            "Token decryption failed. The encryption key may have changed "
            "since this connection was saved — reconnect from the Settings "
            "screen to overwrite with a fresh ciphertext."
        ) from e


def mask_token(plain: str) -> str:
    """`ghp_abc...xyz` style preview used in the UI. Never reveals more than
    the first 4 and last 4 chars; everything else becomes `*`."""
    s = plain.strip()
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * 8}{s[-4:]}"
