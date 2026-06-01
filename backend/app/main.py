"""
GOOPHER API (FastAPI) — the cloud service the Chrome extension talks to, plus
the storefront landing page.

Endpoints:
  POST /auth/login      -> authenticate a customer, return a JWT (T1)
  GET  /auth/me         -> validate token, return the customer
  POST /chat            -> one conversational turn (unified agent)
  POST /orders/bulk     -> high-volume order status (Req 3)
  GET  /catalog         -> public multi-department catalog (storefront)
  GET  /healthz         -> liveness/readiness for Cloud Run
  GET  /metrics         -> lightweight metrics (T10 observability)
  GET  /                -> static storefront landing page (clothing + food)

Designed to run on Cloud Run (T14): single container, listens on $PORT,
stateless except for in-process memory (swap to Firestore memory for multi-
instance). CORS is open to the extension origin.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .agents.orchestrator import get_agent_service
from .auth.auth import authenticate, create_access_token, decode_token
from .config import BACKEND_DIR, get_settings
from .db.database import get_repository
from .tools.order_tool import bulk_order_status
from .models.schemas import (
    BulkOrderQuery,
    ChatRequest,
    ChatResponse,
    LoginRequest,
    TokenResponse,
)
from .observability.telemetry import METRICS, configure_logging, log_event

settings = get_settings()
configure_logging()

app = FastAPI(title="GOOPHER API", version="0.1.0",
              description="Unified conversational retail agent for a multi-department "
                          "(clothing + food) store, used via the GOOPHER Chrome extension.")

# The extension calls cross-origin; allow it. Tighten allow_origins in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Auth dependency
# --------------------------------------------------------------------------- #
def current_customer(authorization: str = Header(default="")) -> dict:
    """Validate the Bearer JWT and return the customer claims (T1)."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return claims


# --------------------------------------------------------------------------- #
# Startup: ensure DB is seeded
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def _startup() -> None:
    get_repository()  # builds & seeds (SQLite) or connects (Firestore)
    get_agent_service()  # warm the orchestrator / backends
    log_event("startup", environment=settings.environment, db=settings.db_backend)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}


@app.get("/metrics")
def metrics() -> dict:
    """Plain JSON metrics (scrape-friendly). Cloud Monitoring can ingest these."""
    return {"metrics": METRICS}


@app.get("/catalog")
def catalog() -> dict:
    """
    Public storefront catalog (no auth) used by the GOOPHER landing page.

    Returns every product grouped by department ("Clothing", "Food") with a
    computed total-stock figure per item so the site can show availability.
    """
    repo = get_repository()
    grouped: dict[str, list[dict]] = {}
    for p in repo.list_products():
        item = p.model_dump()
        item["total_stock"] = sum(v.stock for v in p.variants)
        grouped.setdefault(p.department, []).append(item)
    return {"departments": list(grouped.keys()), "catalog": grouped}


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    customer = authenticate(body.email, body.password)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = create_access_token(customer)
    log_event("login", customer_id=customer.customer_id)
    return TokenResponse(access_token=token, customer=customer)


@app.get("/auth/me")
def me(claims: dict = Depends(current_customer)) -> dict:
    return {"customer_id": claims["sub"], "email": claims.get("email"),
            "name": claims.get("name"), "language": claims.get("lang", "en")}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, claims: dict = Depends(current_customer)) -> ChatResponse:
    """Main entry point for the unified conversational agent.

    When the request omits `language`, we leave it as None so the language
    subagent auto-detects it (and falls back to the session's remembered
    language) inside the orchestrator.
    """
    service = get_agent_service()
    return service.run_turn(req, customer_id=claims["sub"])


@app.post("/orders/bulk")
def orders_bulk(body: BulkOrderQuery, claims: dict = Depends(current_customer)) -> dict:
    """High-volume order management endpoint (Req 3)."""
    log_event("orders_bulk_request", customer_id=claims["sub"], count=len(body.order_ids))
    return bulk_order_status(body.order_ids)


# --------------------------------------------------------------------------- #
# Storefront landing page (static)
# --------------------------------------------------------------------------- #
# Serve the GOOPHER store site at "/" so it has a real http origin that the
# Chrome extension can operate on. The site is a plain storefront; the
# conversational assistant is provided by the GOOPHER *extension* (side panel),
# not embedded here. Mounted last so it never shadows the API routes above.
_SITE_DIR = BACKEND_DIR.parent / "site"
if _SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_SITE_DIR), html=True), name="store")


# Local dev entry point: `python -m backend.app.main`
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=False)
