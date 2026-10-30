"""Environment-driven settings (docs/08): four secrets for the MVP, everything else optional."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ("YOUTUBE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY")
SECRET_KEYS = ("YOUTUBE_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "SUPABASE_DB_URL")


def load_dotenv(path: str | Path = ".env", environ: dict[str, str] | None = None) -> None:
    """Minimal ``KEY=value`` loader; real environment variables always win."""
    env = os.environ if environ is None else environ
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        env.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str
    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    lang: str = "vi"
    max_ideas: int = 5
    git_sha: str = "local"
    trigger: str = "workflow_dispatch"
    image_upload_url: str = "https://nobinobi.vn/shop-service/api/v1/files/upload"

    def secret_values(self) -> list[str]:
        return [
            v for v in (self.youtube_api_key, self.supabase_service_role_key, self.gemini_api_key)
            if v
        ]


class MissingSettings(ValueError):
    def __init__(self, names: list[str]):
        super().__init__("missing environment variables: " + ", ".join(names))
        self.names = names


def from_env(environ: Mapping[str, str] | None = None, require: tuple[str, ...] = REQUIRED) -> Settings:
    env = os.environ if environ is None else environ
    missing = [k for k in require if not env.get(k, "").strip()]
    if missing:
        raise MissingSettings(missing)

    def get(key: str, default: str = "") -> str:
        return env.get(key, default).strip() or default

    try:
        max_ideas = int(get("FLASHTREND_MAX_IDEAS", "5"))
    except ValueError as exc:
        raise ValueError("FLASHTREND_MAX_IDEAS must be an integer") from exc
    if not 1 <= max_ideas <= 20:
        raise ValueError("FLASHTREND_MAX_IDEAS must be between 1 and 20")
    github_event = get("GITHUB_EVENT_NAME")
    return Settings(
        youtube_api_key=get("YOUTUBE_API_KEY"),
        supabase_url=get("SUPABASE_URL"),
        supabase_service_role_key=get("SUPABASE_SERVICE_ROLE_KEY"),
        gemini_api_key=get("GEMINI_API_KEY"),
        gemini_model=get("GEMINI_MODEL", "gemini-2.5-flash"),
        lang=get("FLASHTREND_LANG", "vi"),
        max_ideas=max_ideas,
        git_sha=get("GITHUB_SHA", "local")[:7] or "local",
        trigger="schedule" if github_event == "schedule" else "workflow_dispatch",
        image_upload_url=get(
            "IMAGE_HOST_URL", "https://nobinobi.vn/shop-service/api/v1/files/upload"
        ),
    )
