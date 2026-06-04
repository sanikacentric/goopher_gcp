"""
Shopping-Advisor Subagent — explicit ReAct via ADK's PlanReActPlanner (NEW,
fully self-contained).

WHY THIS EXISTS
---------------
The production agents (`orchestrator.py`) are **native function-calling
`LlmAgent`s** — fast, reliable, no brittle text parsing — and the transactional
path (checkout/fulfillment) is deliberately deterministic. This module adds ONE
extra agent that showcases the OTHER agent style on the SAME Gemini 2.5 Flash: an
**explicit ReAct agent** (`PlanReActPlanner`) that visibly PLANS → ACTS over
tools → REASONS → ANSWERS.

It is the right place for ReAct because shopping advice is:
  * READ-ONLY  — it recommends, it never places an order (no money moves), and
  * MULTI-HOP  — "a healthy snack under $4 that pairs with my last order" needs
                 several tool calls, so the plan is real, not theater.

ISOLATION GUARANTEE
-------------------
  * Brand-new module + its own `InMemoryRunner` (app_name "goopher-advisor").
  * Reuses only READ-ONLY tools (inventory search/details + order lookup).
  * Reached by its own `POST /advise` endpoint — NOT `/chat`, NOT `/vision`.
  * Imports google-adk lazily, so the service still boots where ADK is absent.
Nothing here touches the existing 5 working agents or any checkout code.
"""
from __future__ import annotations

import os
from typing import Optional

from ..config import get_settings
from ..observability.telemetry import incr, log_event, span
from .skills import inventory_skill, order_skill

_settings = get_settings()


ADVISOR_INSTRUCTION = """
You are GOOPHER's Shopping Advisor — a thoughtful retail concierge for a store
with THREE departments: women's casual Clothing, Food/Snacks, and Toys.

Your job is to give a genuinely helpful RECOMMENDATION. Reason step by step:
  1. If the shopper refers to past purchases ("what I ordered last time",
     "goes with my usual"), look up their order history first
     (order_list_for_customer — the signed-in customer_id is given to you in
     context; never ask for it).
  2. Search the live inventory for candidate products (search_inventory). Apply
     any constraints they gave — department, color/size, flavor, max price.
  3. Compare the candidates on price, stock, rating, and how well they fit the
     request, then pick the BEST one or two and explain WHY.

Rules:
  * RECOMMEND ONLY — you must NEVER place, modify, or cancel an order. If they
    want to buy, tell them to say "place an order of <item>" in the main chat.
  * Use ONLY facts returned by your tools — never invent products, prices, or
    stock. Quote the real sale price and flag low stock.
  * Keep the FINAL answer SHORT: a bulleted list, one line per item, naming each
    recommended product and its price (e.g. "• Cheez-It Original — $3.49"). Add at
    most a few words on why it fits. Do NOT write long paragraphs. A one-line
    intro before the list is fine (e.g. "Since you bought Oreos, here are a few
    snacks under $4:").
""".strip()


# --------------------------------------------------------------------------- #
# Lazy singletons (built on first /advise call, reused thereafter)
# --------------------------------------------------------------------------- #
_runner = None
_ready = False
_sessions: set[str] = set()
_LAST_ERROR = ""


def _configure_genai_env() -> None:
    """Point google-genai at Vertex AI (prod) or AI Studio (local), exactly like
    the orchestrator does — so the advisor authenticates the same way."""
    if _settings.use_vertexai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if _settings.google_cloud_project:
            os.environ["GOOGLE_CLOUD_PROJECT"] = _settings.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = _settings.vertex_location
    else:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        if _settings.google_api_key:
            os.environ["GOOGLE_API_KEY"] = _settings.google_api_key


def _react_generate_config():
    """Generate-config for the ReAct agent.

    CRITICAL: gemini-2.5-flash's *thinking* collides with PlanReActPlanner. The
    model emits the PLANNING block + the first ACTION (a tool call), but on the
    turn AFTER the tool returns, thinking spends the output budget and the visible
    /*FINAL_ANSWER*/ never lands — so you get "plan but no answer". DISABLE
    thinking (thinking_budget=0) and give a generous max_output_tokens so the
    planner reliably reasons over the observation and produces the final answer.
    (Same fix proven on the Vision subagent — see vision_agent.py / LEARNINGS §3.16.)
    """
    from google.genai import types

    kwargs = {"max_output_tokens": 4096, "temperature": 0.2}
    try:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:  # older SDK without ThinkingConfig — the budget still helps
        pass
    return types.GenerateContentConfig(**kwargs)


def _gemini_client(settings):
    """A google.genai client on Vertex (prod) or AI Studio (local) — same pattern
    as the Vision subagent. Returns None if no credentials are available."""
    from google import genai

    if settings.use_vertexai:
        return genai.Client(vertexai=True, project=settings.google_cloud_project,
                            location=settings.vertex_location)
    if settings.google_api_key:
        return genai.Client(api_key=settings.google_api_key)
    return None


def _synthesize_recommendation(question: str, observations: list, settings) -> str:
    """SAFETY NET: if the ReAct planner emits a plan but stops before a final
    answer, turn the tool observations (orders + inventory the agent already
    fetched) into a concise, GROUNDED recommendation with one guaranteed
    completion call (thinking disabled so it can't stall again). Returns "" if it
    can't run — the caller then shows a graceful message."""
    import json

    client = _gemini_client(settings)
    if client is None or not observations:
        return ""
    from google.genai import types

    obs_text = json.dumps(observations, default=str)[:6000]
    prompt = (
        "You are GOOPHER's shopping advisor. The shopper asked:\n"
        f"  {question}\n\n"
        "Your tools already returned this data (order history and/or inventory):\n"
        f"{obs_text}\n\n"
        "Using ONLY products present in that data (never invent items), recommend "
        "a few that fit. Reply with a SHORT bulleted list of product names and "
        "their prices only, e.g. '- Cheez-It Original - $3.49'. One short intro "
        "line is fine. No long explanation."
    )
    cfg_kwargs = {"max_output_tokens": 1024, "temperature": 0.2}
    try:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass
    try:
        resp = client.models.generate_content(
            model=settings.gemini_model, contents=[prompt],
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        cands = getattr(resp, "candidates", None) or []
        if cands and getattr(cands[0], "content", None):
            parts = getattr(cands[0].content, "parts", None) or []
            return "".join(getattr(p, "text", "") or "" for p in parts).strip()
    except Exception as exc:  # noqa: BLE001
        log_event("advisor_synthesis_failed", reason=str(exc))
    return ""


def _build_advisor():
    """Construct the single ReAct LlmAgent (PlanReActPlanner) with READ-ONLY tools."""
    _configure_genai_env()
    from google.adk.agents import LlmAgent
    from google.adk.planners import PlanReActPlanner

    return LlmAgent(
        name="shopping_advisor",
        model=_settings.gemini_model,            # same Gemini 2.5 Flash as production
        planner=PlanReActPlanner(),              # <-- EXPLICIT ReAct (visible plan)
        # Disable thinking so the post-tool turn produces a real FINAL_ANSWER.
        generate_content_config=_react_generate_config(),
        description="Read-only shopping advisor that plans, searches inventory and "
                    "order history, reasons, and recommends a product.",
        instruction=ADVISOR_INSTRUCTION,
        # READ-ONLY tools only — NO checkout/place-order tool is ever given here.
        tools=inventory_skill.get_tools() + order_skill.get_tools(),
    )


def _ensure_runner() -> bool:
    """Build the runner once. Returns True if the ReAct advisor is available."""
    global _runner, _ready, _LAST_ERROR
    if _ready:
        return True
    try:
        from google.adk.runners import InMemoryRunner

        agent = _build_advisor()
        _runner = InMemoryRunner(agent=agent, app_name="goopher-advisor")
        _ready = True
        log_event("advisor_init", path="adk-react", model=_settings.gemini_model)
        return True
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash boot
        _LAST_ERROR = f"{type(exc).__name__}: {str(exc)[:200]}"
        log_event("advisor_unavailable", reason=str(exc))
        return False


# --------------------------------------------------------------------------- #
# ReAct output parsing — split the PlanReActPlanner tags into a readable plan
# and the customer-facing final answer.
# --------------------------------------------------------------------------- #
_TAG_LABELS = [
    ("/*PLANNING*/", "🗂 PLAN"),
    ("/*REPLANNING*/", "🔁 REPLAN"),
    ("/*ACTION*/", "⚙️ ACTION"),
    ("/*REASONING*/", "🧠 REASONING"),
    ("/*FINAL_ANSWER*/", "✅ FINAL ANSWER"),
]
_FINAL_TAG = "/*FINAL_ANSWER*/"


def _split_react(raw: str) -> tuple[str, str]:
    """Return (final_answer, pretty_plan). The plan is everything the model
    reasoned BEFORE its final answer, with the raw tags turned into headers so it
    reads nicely in the UI. Robust to the tags being absent."""
    text = (raw or "").strip()
    if not text:
        return "", ""
    has_tags = any(tag in text for tag, _ in _TAG_LABELS)
    if _FINAL_TAG in text:
        idx = text.rindex(_FINAL_TAG)
        final = text[idx + len(_FINAL_TAG):].strip()
        plan_src = text[:idx].strip()
    elif has_tags:
        # The model emitted a plan but stopped before /*FINAL_ANSWER*/. Route the
        # WHOLE thing to the plan panel and leave `final` empty so the caller can
        # supply a graceful reply — NEVER dump raw /*TAGS*/ into the chat bubble.
        final, plan_src = "", text
    else:
        # No ReAct tags at all → it's just a plain recommendation.
        final, plan_src = text, ""
    # Prettify the plan portion: replace each raw tag with a labelled header.
    pretty = plan_src
    for tag, label in _TAG_LABELS:
        pretty = pretty.replace(tag, f"\n\n{label}\n")
    pretty = "\n".join(line.rstrip() for line in pretty.splitlines()).strip()
    return final, pretty


# --------------------------------------------------------------------------- #
# Public entry point (called by POST /advise)
# --------------------------------------------------------------------------- #
def handle_advise(
    question: str,
    customer_id: str,
    session_id: str,
    channel: str = "web",
    language: str = "en",
) -> dict:
    """
    Run ONE advisor turn through the ReAct (PlanReActPlanner) agent.

    Returns a dict: {ok, reply, plan, used_tools, engine}.
      * reply  — the customer-facing recommendation (the FINAL_ANSWER).
      * plan   — the readable PLAN → ACTION → REASONING trace (for the "watch it
                 think" panel). Empty string if the model didn't emit tags.
    """
    incr("advisor_requests_total")
    if not _ensure_runner():
        return {
            "ok": False,
            "reply": ("The Shopping Advisor needs the Gemini/ADK path enabled "
                      "(LLM_PROVIDER=gemini). " + (_LAST_ERROR or "")).strip(),
            "plan": "",
            "used_tools": [],
            "engine": "unavailable",
        }

    import asyncio

    from google.genai import types

    # Create the ADK session once per session_id (idempotent).
    if session_id not in _sessions:
        try:
            asyncio.run(
                _runner.session_service.create_session(
                    app_name="goopher-advisor", user_id=customer_id, session_id=session_id
                )
            )
        except Exception as exc:  # already exists / transient
            log_event("advisor_session_skipped", reason=str(exc))
        _sessions.add(session_id)

    # The advisor has no separate memory store; pass the signed-in id + the ask.
    prompt = (
        f"Signed-in customer_id: {customer_id}. Channel: {channel}. "
        f"Reply language: {language}.\n\nShopper: {question}"
    )
    content = types.Content(role="user", parts=[types.Part(text=prompt)])

    used_tools: list[str] = []
    transcript: list[str] = []      # accumulate ALL model text (plan + final)
    observations: list = []         # tool results, for the synthesis safety net
    try:
        with span("advisor.react_turn"):
            for event in _runner.run(
                user_id=customer_id, session_id=session_id, new_message=content
            ):
                if getattr(event, "get_function_calls", None):
                    for fc in event.get_function_calls() or []:
                        used_tools.append(fc.name)
                if getattr(event, "get_function_responses", None):
                    for fr in event.get_function_responses() or []:
                        observations.append({"tool": getattr(fr, "name", "?"),
                                             "result": getattr(fr, "response", None)})
                if event.content and event.content.parts:
                    txt = "".join(p.text or "" for p in event.content.parts)
                    if txt.strip():
                        transcript.append(txt)
    except Exception as exc:  # noqa: BLE001
        log_event("advisor_turn_failed", reason=str(exc))
        return {
            "ok": False,
            "reply": "Sorry — the advisor hit an error reasoning about that. "
                     "Please try rephrasing your request.",
            "plan": "",
            "used_tools": used_tools,
            "engine": "adk-react",
        }

    raw = "\n".join(transcript).strip()
    reply, plan = _split_react(raw)
    # SAFETY NET: the planner produced a plan but no final answer (the classic
    # "plan but no action" stall). Synthesize a grounded recommendation from the
    # tool observations the agent already gathered, so the shopper still gets a
    # real answer — and keep the plan visible in the panel.
    if not reply:
        synthesized = _synthesize_recommendation(question, observations, get_settings())
        if synthesized:
            reply = synthesized
            log_event("advisor_synthesized", tools=",".join(used_tools))
        else:
            reply = "I couldn't finalize a pick this time — tap 🧠 again, or give " \
                    "me a budget or category (e.g. \"a snack under $4\")."
    log_event("advisor_reply", tools=",".join(used_tools), has_plan=bool(plan))
    return {
        "ok": True,
        "reply": reply,
        "plan": plan,
        "used_tools": used_tools,
        "engine": "adk-react",
    }
