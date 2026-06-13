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

import asyncio
import json

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agents.orchestrator import get_agent_service
from .auth.auth import authenticate, create_access_token, decode_token
from .config import APP_DIR, BACKEND_DIR, get_settings
from .middleware import RateLimitMiddleware
from .observability.flow_recorder import get_recorder, record_login
from .db.database import get_repository
from .tools.order_tool import bulk_order_status
from .models.schemas import (
    AdviseRequest,
    AdviseResponse,
    BulkOrderQuery,
    ChatRequest,
    ChatResponse,
    CriticAnswerRequest,
    CriticFlagRequest,
    LoginRequest,
    TokenResponse,
    VisionRequest,
)
from .observability.telemetry import METRICS, configure_logging, log_event

settings = get_settings()
configure_logging()

app = FastAPI(title="GOOPHER API", version="0.1.0",
              description="Unified conversational retail agent for a multi-department "
                          "(clothing + food) store, used via the GOOPHER Chrome extension.")

# Abuse protection: request-size + per-client rate limiting (DoS / cost-DoS).
# Added before CORS so limits apply to every request.
app.add_middleware(RateLimitMiddleware)

# The extension calls cross-origin; allow it. Tighten allow_origins in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_guardian_probe() -> None:
    """Background self-healing probe: periodically lets Guardian heal forward
    (restore to primary once a fault clears). Isolated from all real flows."""
    if not settings.dev_portal_enabled:
        return
    from .agents.guardian import get_guardian

    async def _loop():
        g = get_guardian()
        while True:
            await asyncio.sleep(4.0)
            try:
                g.tick()
            except Exception:  # never let the probe crash the app
                pass

    asyncio.create_task(_loop())


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


# Build marker — bump when verifying a deploy actually rolled out. Hit
# GET /version on the live service to confirm which code Cloud Run is running.
BUILD_VERSION = "2026-06-04-rsi-plain-decline"


@app.get("/version")
def version() -> dict:
    return {"build": BUILD_VERSION}


@app.get("/metrics")
def metrics() -> dict:
    """Plain JSON metrics (scrape-friendly). Cloud Monitoring can ingest these."""
    return {"metrics": METRICS}


@app.get("/skills")
def skills() -> dict:
    """Introspect the AGENT SKILL REGISTRY — the named capabilities (with their
    tools) that agents pick from. Read-only metadata; powers docs / the dev portal
    and proves which skills are read-only vs transactional."""
    from .agents.skills import agent_skill_registry
    return {"skills": agent_skill_registry.describe()}


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


# --------------------------------------------------------------------------- #
# High-volume scale simulation — READ-ONLY · NO LLM · NO WRITES
# --------------------------------------------------------------------------- #
# These endpoints let a load generator drive thousands of concurrent
# "conversations" to PROVE Cloud Run autoscaling (100 → 10,000 users) without
# burning LLM quota or mutating data. They mirror the real deterministic routing
# + a real catalog/order lookup, so the app + DB path is exercised under load.
# Gated by settings.scale_sim_enabled. Nothing here touches the production flows.
import threading as _threading
import time as _time_mod

_sim_lock = _threading.Lock()
_sim_served = 0
_sim_started = _time_mod.time()


def _sim_incr() -> int:
    global _sim_served
    with _sim_lock:
        _sim_served += 1
        return _sim_served


@app.api_route("/sim/chat", methods=["GET", "POST"])
def sim_chat(message: str = "do you have oreo cookies", mode: str = "browse") -> dict:
    """HIGH-VOLUME LOAD SIMULATION (read-only, no LLM, no writes).

    `mode=browse` → product-support traffic (real catalog search);
    `mode=order_status` → order-management traffic (real order lookup).
    Returns the deterministic route it WOULD take + a real result count, so a
    load test exercises the genuine request + DB path at scale, cheaply."""
    if not settings.scale_sim_enabled:
        raise HTTPException(status_code=404, detail="scale simulation disabled")
    served = _sim_incr()
    repo = get_repository()
    if mode == "order_status":
        routed = "order_agent"
        result = {"orders": len(repo.list_orders_for_customer("CUST-1001"))}
    else:
        from .tools.inventory_tool import search_inventory
        routed = "inventory_agent"
        result = {"matches": search_inventory(query=message).get("count", 0)}
    return {"ok": True, "sim": True, "routed_to": routed, "served": served, **result}


@app.get("/sim/stats")
def sim_stats() -> dict:
    """Live scale counters for the demo: catalog volume + simulated load served."""
    if not settings.scale_sim_enabled:
        raise HTTPException(status_code=404, detail="scale simulation disabled")
    repo = get_repository()
    products = repo.list_products()
    return {
        "products": len(products),
        "variants": sum(len(p.variants) for p in products),
        "departments": sorted({p.department for p in products}),
        "sim_requests_served": _sim_served,
        "uptime_seconds": round(_time_mod.time() - _sim_started, 1),
        "backend": settings.db_backend,
        "model": settings.gemini_model,
    }


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    customer = authenticate(body.email, body.password)
    if not customer:
        record_login(customer_id="", email=body.email, ok=False)  # dev portal
        log_event("login_rejected", email=body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = create_access_token(customer)
    record_login(customer_id=customer.customer_id, email=body.email, ok=True)
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
    # Cap a single message's length so one request can't balloon LLM cost even
    # if it slipped under the body-size limit.
    if len(req.message or "") > settings.max_chat_message_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Message too long (max {settings.max_chat_message_chars} characters).",
        )
    service = get_agent_service()
    return service.run_turn(req, customer_id=claims["sub"])


@app.post("/critic/flag")
def critic_flag(req: CriticFlagRequest, claims: dict = Depends(current_customer)) -> dict:
    """RSI — flag a conversation as unsatisfactory (records a failure for the
    CriticAgent). Isolated: does not touch /chat or any live flow."""
    from .agents.critic_agent import get_critic
    rec = get_critic().record_failure(
        conversation_text=req.conversation_text, csat_score=req.csat_score,
        agent_name=req.agent_name, session_id=req.session_id or "")
    return {"ok": True, "flagged_id": rec["id"]}


@app.post("/critic/heal")
def critic_heal(claims: dict = Depends(current_customer)) -> dict:
    """RSI — run one self-improvement cycle: Gemini-as-judge evaluates each
    pending failure and stores a confidence-gated corrective lesson. Returns the
    lessons learned this cycle (for the live demo)."""
    from .agents.critic_agent import get_critic
    stats = get_critic().run_healing_cycle()
    log_event("critic_heal", evaluated=stats["evaluated"], stored=stats["stored"])
    return {"ok": True, **stats}


@app.get("/critic/lessons")
def critic_lessons(claims: dict = Depends(current_customer)) -> dict:
    """RSI — the learned-lessons knowledge base (what GOOPHER taught itself)."""
    from .agents.critic_agent import get_store
    lessons = get_store().all_lessons()
    return {"count": len(lessons), "lessons": lessons}


@app.post("/critic/answer")
def critic_answer(req: CriticAnswerRequest, claims: dict = Depends(current_customer)) -> dict:
    """RSI — answer a question with learned lessons injected (lesson_retrieve /
    RAG). Self-contained demo of the loop's payoff; does not use /chat."""
    from .agents.critic_agent import get_critic
    out = get_critic().answer_with_lessons(req.message, language=req.language)
    return {"ok": True, **out}


@app.post("/orders/bulk")
def orders_bulk(body: BulkOrderQuery, claims: dict = Depends(current_customer)) -> dict:
    """High-volume order management endpoint (Req 3)."""
    log_event("orders_bulk_request", customer_id=claims["sub"], count=len(body.order_ids))
    return bulk_order_status(body.order_ids)


@app.post("/vision", response_model=ChatResponse)
def vision(req: VisionRequest, claims: dict = Depends(current_customer)) -> ChatResponse:
    """
    Vision subagent (camera "see it, shop it"). The customer points the camera at
    a toy/food item and either asks its price or says "place an order"; Gemini
    Vision recognizes it and the request is answered or ordered. Separate from
    /chat so the existing pipeline is untouched.
    """
    if not req.image_b64:
        raise HTTPException(status_code=400, detail="No image provided.")
    from .agents.vision_agent import handle_vision
    lang = req.language or "en"
    result = handle_vision(
        question=req.question, image_b64=req.image_b64, mime_type=req.mime_type,
        customer_id=claims["sub"], session_id=req.session_id,
        channel=req.channel, language=lang,
    )
    log_event("vision_request", customer_id=claims["sub"],
              recognized=bool(result.get("recognized")))
    return ChatResponse(
        reply=result["reply"], session_id=req.session_id, language=lang,
        channel=req.channel, used_tools=result.get("used_tools", []),
        checkout=result.get("checkout"),
    )


@app.post("/advise", response_model=AdviseResponse)
def advise(req: AdviseRequest, claims: dict = Depends(current_customer)) -> AdviseResponse:
    """
    Shopping-Advisor subagent — explicit ReAct (ADK PlanReActPlanner) on Gemini
    2.5 Flash. The shopper asks for an open-ended recommendation; the agent
    PLANS -> ACTS over read-only tools -> REASONS -> ANSWERS, and we return both
    the recommendation AND the visible reasoning plan. Read-only: it never places
    an order. Separate from /chat and /vision so existing flows are untouched.
    """
    if len(req.message or "") > settings.max_chat_message_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Message too long (max {settings.max_chat_message_chars} characters).",
        )
    from .agents.advisor_agent import handle_advise
    lang = req.language or "en"
    result = handle_advise(
        question=req.message, customer_id=claims["sub"], session_id=req.session_id,
        channel=req.channel, language=lang,
    )
    log_event("advise_request", customer_id=claims["sub"], ok=result.get("ok"),
              tools=",".join(result.get("used_tools", [])))
    return AdviseResponse(
        reply=result["reply"], session_id=req.session_id, language=lang,
        plan=result.get("plan", ""), used_tools=result.get("used_tools", []),
        engine=result.get("engine", "adk-react"),
    )


@app.get("/orders/mine")
def orders_mine(claims: dict = Depends(current_customer)) -> dict:
    """
    The signed-in customer's own orders — backs the extension's cart/orders
    panel ("see what I've already ordered"). Authoritative list straight from
    the repository (newly placed orders included), newest first.
    """
    from .tools.order_tool import list_customer_orders
    data = list_customer_orders(claims["sub"])
    orders = sorted(data.get("orders", []),
                    key=lambda o: o.get("order_date", ""), reverse=True)
    log_event("orders_mine", customer_id=claims["sub"], count=len(orders))
    return {"count": len(orders), "orders": orders}


# --------------------------------------------------------------------------- #
# Developer Portal — live end-to-end flow visualizer
# --------------------------------------------------------------------------- #
# A passive observer that shows, in real time, the full pipeline of every
# conversation turn (auth → session → sub-agents → tools → memory → reply).
# Built for a CTO-friendly walkthrough. Gated by settings.dev_portal_enabled.
_DEV_HTML = APP_DIR / "static" / "dev_portal.html"


@app.get("/dev", response_class=HTMLResponse)
def dev_portal() -> HTMLResponse:
    """Serve the developer portal page."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        return HTMLResponse(_DEV_HTML.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dev portal page missing.")


@app.get("/dev/recent")
def dev_recent(limit: int = 50) -> dict:
    """Return the most recent captured flow records (for initial page load)."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    return {"records": get_recorder().recent(limit=limit)}


# RSI (recursive self-improvement) — dev-portal controls (gated by dev_portal_enabled,
# like the Guardian chaos buttons) so the live demo can show + reset learned lessons.
@app.get("/dev/rsi")
def dev_rsi() -> dict:
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    from .agents.critic_agent import get_store
    lessons = get_store().all_lessons()
    return {"count": len(lessons), "lessons": lessons}


@app.api_route("/dev/rsi/reset", methods=["POST", "GET"])
def dev_rsi_reset() -> dict:
    """Wipe the learned-lessons knowledge base — lets the demo show the clean
    before → teach → after arc repeatably. GET is allowed too, so it can be
    triggered by simply visiting the URL during a demo."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    from .agents.critic_agent import get_store
    removed = get_store().clear()
    log_event("rsi_reset", removed=removed)
    return {"ok": True, "removed": removed}


# --------------------------------------------------------------------------- #
# Self-healing Guardian — ISOLATED. Drives synthetic transactions through its
# own resilience policy; touches NO real flow (/chat, /vision, checkout). Powers
# the live health strip + chaos buttons in the dev portal.
# --------------------------------------------------------------------------- #
@app.get("/dev/health")
def dev_health() -> dict:
    """Guardian's component health (for the /dev health strip)."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    from .agents.guardian import get_guardian
    return get_guardian().health()


@app.post("/dev/chaos")
async def dev_chaos(request: Request) -> dict:
    """Inject or clear a chaos fault on a component (demo control)."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    from .agents.guardian import get_guardian
    body = await request.json()
    component = body.get("component", "")
    action = body.get("action", "inject")
    g = get_guardian()
    if action == "clear":
        g.chaos.clear(component)
        if body.get("silent"):
            # Restore cleanly without emitting a heal-forward card (the client
            # animation already showed the recovery).
            g._reset_circuit(component)
            g._mark(component, "healthy", "operational")
        else:
            g.tick()  # probe → heal forward (records a card) when the fault clears
    else:
        # Fresh incident → reset the breaker so the NEXT request always runs the
        # full DETECT→DIAGNOSE→REMEDIATE→VERIFY loop (repeatable demo, not a
        # silent short-circuit from a still-open circuit).
        g._reset_circuit(component)
        g.chaos.inject(component, body.get("fault", "outage"))
        # Reflect the outage on the strip immediately (LED → red) so "Kill X" is
        # visibly felt before the next request comes in and self-heals.
        g._mark(component, "down", "💥 fault injected — next request self-heals")
    return g.health()


@app.post("/dev/heal-demo")
async def dev_heal_demo(request: Request) -> dict:
    """Run a synthetic transaction through a component so the self-healing is
    visible on demand (the heal streams to /dev/stream as a 'heal' record)."""
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    from .agents.guardian import get_guardian
    body = await request.json()
    return get_guardian().simulate(body.get("component", "vertex"))


@app.get("/dev/stream")
async def dev_stream() -> StreamingResponse:
    """
    Server-Sent-Events stream of new flow records as turns happen live.
    The portal opens this once and renders each record as it arrives.
    """
    if not settings.dev_portal_enabled:
        raise HTTPException(status_code=404, detail="Not found.")

    async def event_gen():
        recorder = get_recorder()
        # Start at the current version so we only stream NEW changes; existing
        # records are loaded once via /dev/recent. Tracking by VERSION (not id)
        # lets a record that advances stage-by-stage (e.g. fulfillment) be
        # re-sent so the portal updates that one card instead of duplicating it.
        last_ver = recorder.current_version()
        # Greeting comment so the connection opens immediately.
        yield ": connected\n\n"
        while True:
            snapshot = recorder.current_version()
            for rec in recorder.since(last_ver):
                yield f"data: {json.dumps(rec)}\n\n"
            last_ver = snapshot
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
