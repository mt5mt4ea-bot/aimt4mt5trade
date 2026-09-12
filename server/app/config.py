from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    ea_api_key: str
    admin_api_token: str
    plan_signing_secret: str
    ai_provider: str
    ai_api_base: str
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: float
    analysis_interval_seconds: int
    min_confidence: float
    auto_trading_enabled: bool
    allow_web_enable: bool
    demo_auth_enabled: bool
    demo_admin_email: str
    demo_admin_password: str
    demo_member_email: str
    demo_member_password: str
    session_hours: int


def get_settings() -> Settings:
    _load_env_file()
    project_root = Path(__file__).resolve().parents[2]
    db_value = os.getenv("DATABASE_PATH", "server/data/genesis_ai.db")
    db_path = Path(db_value)
    if not db_path.is_absolute():
        db_path = project_root / db_path
    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "1899")),
        database_path=db_path,
        ea_api_key=os.getenv("EA_API_KEY", "change-me-ea-key"),
        admin_api_token=os.getenv("ADMIN_API_TOKEN", "change-me-admin-token"),
        plan_signing_secret=os.getenv("PLAN_SIGNING_SECRET", "change-me-plan-secret"),
        ai_provider=os.getenv("AI_PROVIDER", "deepseek"),
        ai_api_base=os.getenv("AI_API_BASE", "https://api.deepseek.com").rstrip("/"),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_model=os.getenv("AI_MODEL", "deepseek-v4-flash"),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "35")),
        analysis_interval_seconds=max(30, int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "300"))),
        min_confidence=min(0.95, max(0.5, float(os.getenv("MIN_CONFIDENCE", "0.65")))),
        auto_trading_enabled=_bool("AUTO_TRADING_ENABLED", False),
        allow_web_enable=_bool("ALLOW_WEB_ENABLE", False),
        demo_auth_enabled=_bool("DEMO_AUTH_ENABLED", True),
        demo_admin_email=os.getenv("DEMO_ADMIN_EMAIL", "admin@wisefx.ai").strip().lower(),
        demo_admin_password=os.getenv("DEMO_ADMIN_PASSWORD", "WiseFX@Admin11"),
        demo_member_email=os.getenv("DEMO_MEMBER_EMAIL", "member@wisefx.ai").strip().lower(),
        demo_member_password=os.getenv("DEMO_MEMBER_PASSWORD", "WiseFX@Member11"),
        session_hours=max(1, min(168, int(os.getenv("SESSION_HOURS", "24")))),
    )


settings = get_settings()
