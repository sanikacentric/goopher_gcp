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
from ..observability.telemetry import incr, log_event
from .skills import agent_skill_registry as skills

_settings = get_settings()


ADVISOR_INSTRUCTION = """
You are GOOPHER's Shopping Advisor — a thoughtful retail concierge for a store
with THREE departments: women's casual Clothing, Food/Snacks, and Toys.

Your job is to give a genuinely helpful RECOMMENDATION. Reason step by step:
  1. If the shopper refers to past purchases ("what I ordered last time", "my
     last order", "goes with my usual"), look up their order history first
     (order_list_for_customer — the signed-in customer_id is given to you in
     context; never ask for it). Identify the MOST RECENT order, and note BOTH
     its department (Clothing / Food / Toys) AND the price they paid.
  2. Search the live inventory for candidate products (search_inventory). Match
     the context: recommend from the SAME department as the relevant order and a
     SIMILAR-or-lower price (e.g. a $17.99 Toy → other Toys at/under ~$18, NOT
     snacks). Honor any explicit constraints the shopper gave
     (department / color / size / flavor / max price) instead.
  3. Compare the candidates on price, stock, rating, and fit, then pick the BEST
     two or three.

Rules:
  * RECOMMEND ONLY — you must NEVER place, modify, or cancel an order. If they
    want to buy, tell them to say "place an order of <item>" in the main chat.
  * Use ONLY facts returned by your tools — never invent products, prices, or
    stock. Quote the real sale price and flag low stock. NEVER default to a
    different department than the one the context implies (don't suggest snacks
    for a toy order).
  * Keep the FINAL answer SHORT: a bulleted list, one line per item, naming each
    recommended product and its price (e.g. "• Adidas Match Soccer Ball — $17.99").
    Add at most a few words on why it fits. No long paragraphs. A one-line,
    department-appropriate intro before the list is fine (e.g. "Since you bought a
    soccer ball, here are other toys around that price:").
""".strip()


# --------------------------------------------------------------------------- #
# The advisor runs through the COMMON AgentHarness (scaffolding) — the same
# wrapper the orchestrator uses. Built lazily on first /advise call.
# --------------------------------------------------------------------------- #
from .harness import AgentHarness  # noqa: E402

_HARNESS = AgentHarness(
    name="advisor",
    app_name="goopher-advisor",
    build_agent=lambda: _build_advisor(),
)


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
        "Recommend items that match the CONTEXT: if the question refers to the "
        "shopper's last order, recommend from the SAME department as that order "
        "and a similar-or-lower price (e.g. a $17.99 Toy → other Toys at/under "
        "~$18, NOT snacks). Use ONLY products present in the data above — never "
        "invent items, and never switch departments. Reply with a SHORT bulleted "
        "list of product names and their prices only, e.g. '- Adidas Match Soccer "
        "Ball - $17.99'. One short intro line is fine. No long explanation."
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


def _advisor_tools() -> list:
    """Pick the advisor's tools from the registry — ONLY read-only skills, so the
    advisor can never be handed a checkout/place-order tool. We assert the skills
    we use are flagged read_only, turning the isolation guarantee into code."""
    chosen = ["inventory", "order"]
    for name in chosen:
        assert skills.get_skill(name).read_only, f"advisor skill '{name}' must be read-only"
    return skills.get_tools(*chosen)


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
        # READ-ONLY skills only (from the registry) — NO checkout tool is ever given.
        tools=_advisor_tools(),
    )


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

    # The advisor has no separate memory store; pass the signed-in id + the ask.
    prompt = (
        f"Signed-in customer_id: {customer_id}. Channel: {channel}. "
        f"Reply language: {language}.\n\nShopper: {question}"
    )

    # Run through the COMMON harness (build → session → run-loop → collect). The
    # advisor is READ-ONLY, so a retry on a transient error is safe.
    result = _HARNESS.run(user_id=customer_id, session_id=session_id,
                          prompt=prompt, retries=2)

    if not result.ok:
        if not _HARNESS.ready():
            # Couldn't even build the agent → ADK/Gemini path isn't enabled.
            return {
                "ok": False,
                "reply": ("The Shopping Advisor needs the Gemini/ADK path enabled "
                          "(LLM_PROVIDER=gemini). " + (result.error or "")).strip(),
                "plan": "", "used_tools": [], "engine": "unavailable",
            }
        # Built fine but every attempt errored while reasoning.
        log_event("advisor_turn_failed", reason=result.error)
        return {
            "ok": False,
            "reply": "Sorry — the advisor hit an error reasoning about that. "
                     "Please try rephrasing your request.",
            "plan": "", "used_tools": result.used_tools, "engine": "adk-react",
        }

    reply, plan = _split_react(result.transcript)
    # SAFETY NET: the planner produced a plan but no final answer (the classic
    # "plan but no action" stall). Synthesize a grounded recommendation from the
    # tool observations the agent already gathered, so the shopper still gets a
    # real answer — and keep the plan visible in the panel.
    if not reply:
        synthesized = _synthesize_recommendation(question, result.observations, get_settings())
        if synthesized:
            reply = synthesized
            log_event("advisor_synthesized", tools=",".join(result.used_tools))
        else:
            reply = "I couldn't finalize a pick this time — tap 🧠 again, or give " \
                    "me a budget or category (e.g. \"a snack under $4\")."
    log_event("advisor_reply", tools=",".join(result.used_tools), has_plan=bool(plan))
    return {
        "ok": True,
        "reply": reply,
        "plan": plan,
        "used_tools": result.used_tools,
        "engine": "adk-react",
    }
