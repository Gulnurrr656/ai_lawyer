"""Auth helpers: password hashing + signed session cookie.

We avoid bcrypt/passlib to keep deps minimal. PBKDF2-HMAC-SHA256 is solid
for MVP. Sessions are stored in a signed cookie via ``itsdangerous``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Any, Dict, Optional

try:
    from itsdangerous import BadSignature, TimestampSigner
except Exception:  # pragma: no cover
    BadSignature = Exception  # type: ignore[assignment]
    TimestampSigner = None  # type: ignore[assignment]


_PBKDF2_ITER = 200_000
_HASH_ALGO = "sha256"
SESSION_COOKIE = "zangerpro_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$<iter>$<salt>$<hash>``."""

    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(_HASH_ALGO, password.encode("utf-8"),
                                 salt, _PBKDF2_ITER)
    return "pbkdf2_sha256${iter}${salt}${digest}".format(
        iter=_PBKDF2_ITER,
        salt=base64.b64encode(salt).decode("ascii"),
        digest=base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    if not stored or not password:
        return False
    try:
        algo, iter_s, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iter_n = int(iter_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        candidate = hashlib.pbkdf2_hmac(
            _HASH_ALGO, password.encode("utf-8"), salt, iter_n
        )
        return hmac.compare_digest(expected, candidate)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signed session cookie
# ---------------------------------------------------------------------------

def _signer(secret: str) -> "TimestampSigner":
    if TimestampSigner is None:
        raise RuntimeError(
            "itsdangerous is not installed. `pip install itsdangerous`"
        )
    return TimestampSigner(secret_key=secret, salt="zangerpro-session")


def encode_session(secret: str, payload: Dict[str, Any]) -> str:
    """Encode a session payload (dict) into a signed cookie value."""

    import json

    raw = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return _signer(secret).sign(raw).decode("ascii")


def decode_session(secret: str, signed: str) -> Optional[Dict[str, Any]]:
    """Return the session dict or ``None`` if invalid/expired."""

    if not signed:
        return None
    try:
        raw = _signer(secret).unsign(signed.encode("ascii"),
                                     max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    except Exception:
        return None
    try:
        import json

        return json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))
    except Exception:
        return None


def random_token(n_bytes: int = 24) -> str:
    return secrets.token_urlsafe(n_bytes)


__all__ = [
    "SESSION_COOKIE",
    "SESSION_MAX_AGE",
    "decode_session",
    "encode_session",
    "hash_password",
    "random_token",
    "verify_password",
]
