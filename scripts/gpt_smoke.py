r"""
LLM/OpenAI smoke test for AI_LAWYER.

Usage:
    .\.venv\Scripts\python.exe scripts/gpt_smoke.py            # local checks only
    .\.venv\Scripts\python.exe scripts/gpt_smoke.py --network  # one short Responses call

Prints only success/fail status. Never prints the API key.
Returns exit code 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from app.shared.llm_client import (  # noqa: E402
    MODEL,
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMQuotaError,
    LLMUnavailableError,
    llm_available_smoke_test,
)


def _mask_key(value: str | None) -> str:
    if not value:
        return "(missing)"
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}***{value[-4:]} (len={len(value)})"


async def main() -> int:
    parser = argparse.ArgumentParser(description="LLM smoke test (no secrets printed).")
    parser.add_argument(
        "--network",
        action="store_true",
        help="Make a short Responses API network call (uses quota).",
    )
    args = parser.parse_args()

    import os

    key = os.environ.get("OPENAI_API_KEY")
    print(f"[env] OPENAI_API_KEY: {_mask_key(key)}")
    print(f"[env] OPENAI_MODEL:   {MODEL}")

    info = await llm_available_smoke_test(do_network_call=False)
    print(f"[sdk] Responses API supported: {info['sdk_responses_supported']}")
    print(f"[sdk] AsyncOpenAI client built: {info['client_built']}")
    if info.get("error"):
        print(f"[sdk] error: {info['error']}")
        return 1

    if not args.network:
        print("[result] LOCAL CHECKS OK (use --network for live call)")
        return 0

    try:
        info_net = await llm_available_smoke_test(do_network_call=True)
    except LLMConfigError as e:
        print(f"[result] FAIL: config error -> {e}")
        return 1
    except LLMAuthError as e:
        print(f"[result] FAIL: invalid API key -> {e}")
        return 1
    except LLMQuotaError as e:
        print(f"[result] FAIL: quota/billing -> {e}")
        return 1
    except LLMUnavailableError as e:
        print(f"[result] FAIL: temporarily unavailable -> {e}")
        return 1
    except LLMError as e:
        print(f"[result] FAIL: {type(e).__name__}: {e}")
        return 1
    except Exception as e:  # pragma: no cover
        print(f"[result] FAIL: unexpected error: {type(e).__name__}: {e}")
        return 1

    if info_net.get("error"):
        print(f"[result] FAIL: {info_net['error']}")
        return 1

    if info_net.get("network_call_ok"):
        print("[result] OK: Responses API reachable, model responded.")
        return 0
    print("[result] FAIL: Responses API responded but content unexpected.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
