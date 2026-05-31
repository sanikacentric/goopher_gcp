"""
Central application configuration.

All settings are read from environment variables (12-factor style) so the same
image runs locally, in CI, and on Google Cloud Run without code changes.
Uses pydantic-settings for validation and typed access.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo paths (resolved relative to this file so they work in any CWD / container).
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
DATA_FILE = BACKEND_DIR / "data" / "jcpenney_casual_dresses.json"


class Settings(BaseSettings):
    """Typed application settings, populated from env vars or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    app_name: str = "GOOPHER"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    # --- LLM (Gemini free tier) ---
    # Get a free key at https://aistudio.google.com/app/apikey
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"  # free-tier friendly, fast, multimodal

    # --- Google Cloud (free tier) ---
    google_cloud_project: str = ""
    # "sqlite" for local dev (zero setup) or "firestore" for the GCP free tier.
    db_backend: str = "sqlite"
    sqlite_path: str = str(BACKEND_DIR / "goopher.db")
    firestore_database: str = "(default)"

    # --- Auth ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 1 day

    # --- Observability ---
    enable_tracing: bool = True
    otel_exporter: str = "console"  # console | gcp (Cloud Trace)

    # --- High-volume / batch order management ---
    bulk_max_orders: int = 500  # safety cap for a single high-volume request


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
