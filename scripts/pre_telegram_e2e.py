#!/usr/bin/env python3
"""
Preflight перед ручным Telegram E2E: compileall + smoke качества сценариев.
Не заменяет прогон в боте; только отсеивает синтаксис и сломанные импорты.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "app"],
            cwd=str(ROOT),
            check=True,
        )
    except subprocess.CalledProcessError:
        print("pre_telegram_e2e: compileall FAILED", file=sys.stderr)
        return 1

    smoke = ROOT / "scripts" / "smoke_scenario_quality.py"
    try:
        subprocess.run([sys.executable, str(smoke)], cwd=str(ROOT), check=True)
    except subprocess.CalledProcessError:
        print("pre_telegram_e2e: smoke_scenario_quality FAILED", file=sys.stderr)
        return 1

    print("pre_telegram_e2e: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
