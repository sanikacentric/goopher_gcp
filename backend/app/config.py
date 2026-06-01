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
DATA_FILE = BACKEND_DIR / "data" / "goopher_catalog.json"


class Settings(BaseSettings):
    """Typed application settings, populated from env vars or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    app_name: str = "GOOPHER"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    # --- LLM provider selection ---
    # ALL conversations currently use OpenAI. Set OPENAI_API_KEY in your .env.
    # Get a key at https://platform.openai.com/api-keys
    llm_provider: str = "openai"          # "openai" (active) | "gemini" (future)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"     # fast, low-cost, great for phrasing
    openai_base_url: str = ""             # optional override (Azure/proxy); blank = default

    # --- LLM (Gemini) — set llm_provider="gemini" to use the ADK + Gemini path ---
    # Two ways to authenticate Gemini:
    #   1. AI Studio API key (free tier = only 20 req/day): set GOOGLE_API_KEY.
    #      Get one at https://aistudio.google.com/app/apikey
    #   2. Vertex AI (recommended; uses your $300 GCP credit / high quota):
    #      set USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT + VERTEX_LOCATION, and
    #      authenticate with `gcloud auth application-default login`.
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # fast, multimodal
    use_vertexai: bool = False              # True -> route Gemini/ADK via Vertex AI
    vertex_location: str = "us-central1"

    # When True, try the ADK multi-agent path first and fall back to the grounded
    # path if it errors. Default False = always use the grounded "tools + LLM
    # phrasing" path: it deterministically routes to the right tool (so it never
    # refuses or hallucinates) and uses the LLM for the natural-language reply, so
    # every conversation is still 100% LLM-powered AND grounded in real data.
    # NOTE: the ADK path is Gemini-based, so it stays OFF while using OpenAI.
    use_adk_path: bool = False

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

    # --- Access control (single-user lockdown) ---
    # Only these emails may log in / use the LLM endpoint. Comma-separated.
    # Anyone else is rejected even with a correct password.
    allowed_emails: str = "demo@goopher.app"
    # The master password for the allowed account(s). MUST be set via env /
    # Secret Manager in any deployed environment. If left at this sentinel, the
    # service refuses ALL logins (fail-closed) so a missing password can't leave
    # the endpoint open. Never commit a real password.
    master_password: str = "CHANGE_ME_set_via_env"

    # --- Observability ---
    enable_tracing: bool = True
    otel_exporter: str = "console"  # console | gcp (Cloud Trace)

    # --- High-volume / batch order management ---
    bulk_max_orders: int = 500  # safety cap for a single high-volume request

    # --- Abuse protection / DoS limits ---
    rate_limit_enabled: bool = True
    # Per-client request budgets (sliding window). The LLM /chat path is the
    # expensive one, so it gets a tighter limit than cheap endpoints.
    rate_limit_chat_per_min: int = 20     # /chat requests per client per minute
    rate_limit_global_per_min: int = 120  # all requests per client per minute
    rate_limit_login_per_min: int = 10    # /auth/login attempts per client per min
    # Max request body size (bytes). Blocks oversized payloads (e.g. huge base64
    # attachments) before they reach the app. 2 MB default.
    max_request_bytes: int = 2 * 1024 * 1024
    # Max characters in a single chat message (separate from body size).
    max_chat_message_chars: int = 4000


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
