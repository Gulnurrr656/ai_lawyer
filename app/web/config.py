"""Web app configuration helpers.

All settings come from env vars; no ``BOT_TOKEN`` is required to start the
web server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


WEB_PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_PACKAGE_DIR.parent.parent  # repo root


def _bool(env_name: str, default: bool = False) -> bool:
    raw = (os.environ.get(env_name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class WebConfig:
    app_env: str = "development"
    base_url: str = "http://localhost:8000"
    secret_key: str = ""
    storage_dir: Path = Path("exports")
    upload_dir: Path = Path("var/uploads")
    db_path: Optional[str] = None
    payment_mode: str = "mock"
    kaspi_mode: str = "manual"
    halyk_provider_mode: str = "mock"
    paylink_shop_id: str = ""
    paylink_secret_key: str = ""
    admin_email: str = ""
    admin_password: str = ""
    fake_llm: bool = False
    openai_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def load_config() -> WebConfig:
    cfg = WebConfig(
        app_env=os.environ.get("APP_ENV", "development"),
        base_url=os.environ.get("WEB_BASE_URL", "http://localhost:8000"),
        secret_key=os.environ.get("SECRET_KEY") or "zangerpro-dev-secret-change-me",
        storage_dir=Path(os.environ.get("STORAGE_DIR") or "exports"),
        upload_dir=Path(os.environ.get("UPLOAD_DIR") or "var/uploads"),
        db_path=os.environ.get("ZANGERPRO_DB_PATH") or None,
        payment_mode=os.environ.get("PAYMENT_MODE", "mock"),
        kaspi_mode=os.environ.get("KASPI_MODE", "manual"),
        halyk_provider_mode=os.environ.get("HALYK_PROVIDER_MODE", "mock"),
        paylink_shop_id=os.environ.get("PAYLINK_SHOP_ID", ""),
        paylink_secret_key=os.environ.get("PAYLINK_SECRET_KEY", ""),
        admin_email=os.environ.get("ADMIN_EMAIL", ""),
        admin_password=os.environ.get("ADMIN_PASSWORD", ""),
        fake_llm=_bool("AI_LAWYER_FAKE_LLM", False),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    cfg.storage_dir.mkdir(parents=True, exist_ok=True)
    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    return cfg


__all__ = ["WebConfig", "load_config", "PROJECT_ROOT", "WEB_PACKAGE_DIR"]
