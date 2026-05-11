"""Centralised runtime-mode flags.

Single source of truth for "is this a dev/test run or production?" and for
the per-feature switches that depend on it (payment bypass, voice enabled,
voice mock). The helpers are deliberately tiny so they can be reused
from request handlers, services and tests without circular imports.

Environment contract:

============================ =========================================
Variable                     Effect
============================ =========================================
``APP_ENV``                  ``production`` disables all test bypasses.
``ENVIRONMENT``              Alias for ``APP_ENV`` (some hosts use it).
``ZANGERPRO_TEST_MODE``      ``1`` forces test mode even outside dev.
``ZANGERPRO_BYPASS_PAYMENT`` ``1`` opens access without payment **only**
                             when :func:`is_test_mode` is true.
``ZANGERPRO_VOICE_ENABLED``  ``1`` shows the voice UI. Defaults to true
                             in test mode and false in production unless
                             explicitly set.
``ZANGERPRO_VOICE_MOCK``     ``1`` returns canned mock text when OpenAI
                             is not configured (test mode only).
============================ =========================================

Production safety
-----------------
``is_production()`` returns ``True`` whenever ``APP_ENV`` (or its
``ENVIRONMENT`` alias) equals ``production`` (case-insensitive). In that
state :func:`is_payment_bypass_enabled` **always** returns ``False``,
regardless of ``ZANGERPRO_BYPASS_PAYMENT``, and a warning is logged the
first time the flag is observed.
"""

from __future__ import annotations

import logging
import os
from typing import Set

logger = logging.getLogger("zangerpro.runtime_mode")


_TRUE_VALUES: Set[str] = {"1", "true", "yes", "on"}


# Names of every env variable this module owns. Exposed for diagnostics
# pages (``/dev/voice-test``) and tests.
TEST_MODE_FLAG = "ZANGERPRO_TEST_MODE"
BYPASS_PAYMENT_FLAG = "ZANGERPRO_BYPASS_PAYMENT"
VOICE_ENABLED_FLAG = "ZANGERPRO_VOICE_ENABLED"
VOICE_MOCK_FLAG = "ZANGERPRO_VOICE_MOCK"

# Environment-name slots and the values we treat as "non-production".
_ENV_VAR_NAMES = ("APP_ENV", "ENVIRONMENT")
_TEST_ENV_VALUES: Set[str] = {"dev", "development", "test", "testing", "local"}
_PRODUCTION_ENV_VALUES: Set[str] = {"production", "prod"}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in _TRUE_VALUES


def _current_env_name() -> str:
    """Return the active environment name (lowercase)."""

    for var in _ENV_VAR_NAMES:
        val = _env(var).lower()
        if val:
            return val
    return ""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_production() -> bool:
    """Return ``True`` if the app runs in production.

    Order: explicit ``APP_ENV=production`` (or ``ENVIRONMENT=production``)
    wins. Anything else is *not* considered production.
    """

    env = _current_env_name()
    return env in _PRODUCTION_ENV_VALUES


def is_test_mode() -> bool:
    """Return ``True`` if test/dev bypasses are allowed."""

    if is_production():
        return False
    if _bool_env(TEST_MODE_FLAG):
        return True
    env = _current_env_name()
    return env in _TEST_ENV_VALUES


# Tracks whether we already logged a "bypass attempted in production"
# warning so the log isn't flooded.
_logged_production_bypass_attempt = False


def is_payment_bypass_enabled() -> bool:
    """Return ``True`` only in test mode **and** with the bypass flag set."""

    global _logged_production_bypass_attempt

    bypass_requested = _bool_env(BYPASS_PAYMENT_FLAG)
    if is_production():
        if bypass_requested and not _logged_production_bypass_attempt:
            logger.warning(
                "ZANGERPRO_BYPASS_PAYMENT=1 ignored: APP_ENV=production. "
                "Payment bypass is permanently disabled in production."
            )
            _logged_production_bypass_attempt = True
        return False
    return bypass_requested and is_test_mode()


def is_voice_enabled() -> bool:
    """Return ``True`` when the voice widget should be visible.

    Rules:

    * Explicit ``ZANGERPRO_VOICE_ENABLED=0`` always wins (hide UI).
    * Explicit ``ZANGERPRO_VOICE_ENABLED=1`` always shows the UI.
    * Default: enabled in test mode, **disabled** in production.
    """

    raw = _env(VOICE_ENABLED_FLAG).lower()
    if raw:
        return raw in _TRUE_VALUES
    return is_test_mode()


def is_voice_mock_enabled() -> bool:
    """Mock transcription is allowed only in test mode."""

    return is_test_mode() and _bool_env(VOICE_MOCK_FLAG)


def runtime_snapshot() -> dict:
    """Return a dict describing the active runtime flags.

    Safe for templates and the dev voice-test page — never exposes
    secrets. Used for the UI badge and diagnostics.
    """

    return {
        "app_env": _current_env_name() or "unspecified",
        "is_production": is_production(),
        "is_test_mode": is_test_mode(),
        "payment_bypass": is_payment_bypass_enabled(),
        "voice_enabled": is_voice_enabled(),
        "voice_mock": is_voice_mock_enabled(),
        "openai_configured": bool(_env("OPENAI_API_KEY")),
        "transcribe_model": (
            _env("OPENAI_TRANSCRIBE_MODEL") or "gpt-4o-mini-transcribe"
        ),
    }


__all__ = [
    "BYPASS_PAYMENT_FLAG",
    "TEST_MODE_FLAG",
    "VOICE_ENABLED_FLAG",
    "VOICE_MOCK_FLAG",
    "is_payment_bypass_enabled",
    "is_production",
    "is_test_mode",
    "is_voice_enabled",
    "is_voice_mock_enabled",
    "runtime_snapshot",
]
