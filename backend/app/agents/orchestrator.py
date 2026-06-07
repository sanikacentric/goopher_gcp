"""
GOOPHER Orchestrator (Requirement T2: ADK ORCHESTRATOR FOR AGENTS).

This is the unified conversational agent. It:
  * Composes the inventory & order AGENT SKILLS (T4) as tools.
  * Coordinates three SUBAGENTS — channel (2A-4), language (2A-5), modality
    (2A-6) — to satisfy multi-channel / multi-lingual / multi-modal needs.
  * Uses the MEMORY agent (T3) to maintain context across channel/language/
    modality switches (global "maintain context" requirement).
  * Uses Gemini (T6) as the LLM; inventory/order tools are ADK function tools
    (T5) registered directly on the agent (in-process).
  * Emits traces/metrics for OBSERVABILITY (T10).

Two execution paths share one public method, `run_turn`:
  1. ADK path  — builds a real google-adk LlmAgent tree + Runner. Used when the
                 `google-adk` package and a Gemini API key are available.
  2. Fallback  — a deterministic, dependency-light engine that performs intent
                 routing, calls the same tools, and (optionally) uses Gemini for
                 phrasing. Guarantees the service runs in CI / offline and keeps
                 unit tests hermetic.

Both paths produce identical ChatResponse shapes, go through the same memory,
language, channel, and modality logic, and are fully traced.
"""
from __future__ import annotations

from ..config import BACKEND_DIR, get_settings
from ..memory.memory_agent import Turn, get_memory_store
from ..models.schemas import ChatRequest, ChatResponse
from ..observability.flow_recorder import TurnTrace
from ..observability.telemetry import incr, log_event, span
from . import channel_agent, language_agent, modality_agent
from .skills import agent_skill_registry as skills

_settings = get_settings()


ROOT_INSTRUCTION = """
You are GOOPHER, a friendly, efficient shopping assistant for an online store
with THREE departments: women's casual Clothing, Food/Snacks, and Toys. You help
customers discover products in ANY department, check live inventory, and manage
their orders (single or in bulk).

The store sells clothing (dresses), food/snacks (chips, cookies, soda, peanuts,
crackers, snack bars), AND toys (soccer ball, LEGO, NERF, Play-Doh, Hot Wheels,
puzzles). NEVER say you only sell one category.
Be concise and proactive. Surface low-stock warnings and the current sale price.
Stay on the topic of the store's clothing, food, and toy products and order help.
""".strip()


# How the ROOT orchestrator must DELEGATE. It owns no retail tools itself — it
# picks a worker sub-agent for the task; the worker calls the tools.
ORCHESTRATOR_DELEGATION = """
You are GOOPHER, the MAIN orchestrator agent, in charge of the turn. You SELECT
and DELEGATE to the right WORKER sub-agent (each is a tool you call), then
compose the final customer-facing reply.

For every turn:
- product availability / price / stock / "do you have…" / "show me…"
  -> delegate to `inventory_agent` (it owns the inventory tools).
- order status / tracking / "where is my order" / bulk orders
  -> delegate to `order_agent` (it owns the order tools).
- "place an order" / "buy" / "checkout" / "order this" (single item), OR
  "place bulk order" / "order multiple" / "buy several" (many items at once)
  -> delegate to `checkout_agent` (it adds to cart, takes payment, places it;
     use place_bulk_order for the bulk variants).

The customer's language and channel formatting directive are provided to you in
context (detected during pre-processing) — honor them in your reply. You are the
decision-maker; the workers are your sub-agents. Never invent product or order
facts — use only what the worker returned. Never claim the store sells only one
category.
""".strip()


# --------------------------------------------------------------------------- #
# ADK agent tree
# --------------------------------------------------------------------------- #
def build_root_agent():
    """
    Construct the ADK multi-agent tree. goopher_orchestrator is the ROOT/main
    agent; all others are sub-agents under it (exposed as AgentTools):

        goopher_orchestrator (ROOT, Gemini)
          ├─ memory_agent     ──► recall_session_memory
          ├─ modality_agent   ──► detect_modality
          ├─ language_agent   ──► detect_language
          ├─ inventory_agent  ──owns──► inventory tools
          ├─ order_agent      ──owns──► order tools
          └─ channel_agent    ──► select_channel

    The orchestrator coordinates these sub-agents (per its instruction: memory →
    modality → language → worker → channel) and composes the final reply. Worker
    sub-agents OWN and call the retail tools. Shows in traces as:
    invoke_agent goopher_orchestrator → invoke_agent inventory_agent →
    execute_tool search_inventory.

    Imported lazily so the module loads even where google-adk isn't installed.
    """
    import os

    # Tell ADK / google-genai whether to use Vertex AI (the $300-credit / high
    # quota path) or the AI Studio API key. ADK reads these from the environment.
    if _settings.use_vertexai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if _settings.google_cloud_project:
            os.environ["GOOGLE_CLOUD_PROJECT"] = _settings.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = _settings.vertex_location
    else:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        if _settings.google_api_key:
            os.environ["GOOGLE_API_KEY"] = _settings.google_api_key

    from google.adk.agents import LlmAgent
    from google.adk.tools.agent_tool import AgentTool

    model = _settings.gemini_model

    # --- Worker sub-agents that OWN the tools ---
    # Each worker PICKS its skill from the agent skill registry (single source of
    # truth) and binds that skill's tools + instruction.
    inv = skills.get_skill("inventory")
    order = skills.get_skill("order")
    checkout = skills.get_skill("checkout")
    fulfillment = skills.get_skill("fulfillment")

    # inventory_agent owns the inventory tools and calls them itself.
    inventory_agent = LlmAgent(
        name="inventory_agent",
        model=model,
        description="Specialist that answers product availability, price, and "
                    "stock questions by calling the inventory tools.",
        instruction=(
            "You are the inventory specialist for a store with THREE departments — "
            "Clothing, Food/Snacks, AND Toys (soccer ball, LEGO, NERF, Play-Doh, "
            "Hot Wheels, puzzles). Use your tools to answer the request:\n"
            + inv.instruction
            + "\nReturn the concrete results (names, prices, stock). ALWAYS trust "
              "the tool output. NEVER say the store doesn't sell toys or only "
              "sells one/two categories — it sells clothing, food, AND toys."
        ),
        tools=inv.get_tools(),
    )

    # order_agent owns the order tools and calls them itself.
    order_agent = LlmAgent(
        name="order_agent",
        model=model,
        description="Specialist that answers order-status and order-management "
                    "questions (single or bulk) by calling the order tools.",
        instruction=(
            "You are the order-management specialist. Use your tools to answer:\n"
            + order.instruction
            + "\nThe signed-in customer_id is provided in context; never ask for it."
        ),
        tools=order.get_tools(),
    )

    # checkout_agent owns the checkout tools (add to cart, simulated payment,
    # place order) — used when the customer says "place an order".
    checkout_agent = LlmAgent(
        name="checkout_agent",
        model=model,
        description="Specialist that places an order: adds to cart, runs the "
                    "(simulated) payment, and confirms the placed order.",
        instruction=(
            "You are the checkout specialist. Use your tools to place orders:\n"
            + checkout.instruction
            + "\nThe signed-in customer_id is provided in context; never ask for it."
        ),
        tools=checkout.get_tools(),
    )

    # order_management_agent owns the fulfillment pipeline (runs after payment):
    # validate -> inventory check -> insert ORDER_PLACED -> confirm -> warehouse
    # -> ship -> track -> deliver -> invoice. Checkout triggers it automatically;
    # it's also exposed so the orchestrator can run/re-run fulfillment on request.
    order_management_agent = LlmAgent(
        name="order_management_agent",
        model=model,
        description="Specialist that runs the post-payment fulfillment pipeline "
                    "(validation, inventory check, ORDER_PLACED insert, shipping, "
                    "delivery, invoice).",
        instruction=(
            "You manage order fulfillment after payment.\n"
            + fulfillment.instruction
            + "\nThe signed-in customer_id is provided in context."
        ),
        tools=fulfillment.get_tools(),
    )

    # --- ROOT: goopher_orchestrator — the MAIN unified agent ---
    # It coordinates the WORKER sub-agents (inventory, order) — the agents that do
    # real reasoning over tools — and composes the reply. These two are reliable
    # ADK LlmAgents (proven in traces).
    #
    # NOTE: memory / modality / language / channel are handled by DETERMINISTIC
    # pre-processing in run_turn (fast pure-Python, no LLM) — NOT as ADK
    # sub-agents. We tried them as LlmAgents and they kept failing ('no text
    # response' + per-turn context-binding issues across ADK's execution context),
    # for zero benefit since that work needs no intelligence. Keeping them
    # deterministic makes the system reliable and free, and they are shown
    # separately ("pre-process") in the dev portal.
    orchestrator = LlmAgent(
        name="goopher_orchestrator",
        model=model,
        description="The main unified GOOPHER agent. Selects the right worker "
                    "sub-agent (inventory, order, or checkout), and composes the "
                    "customer-facing reply for clothing & food retail.",
        instruction=ROOT_INSTRUCTION + "\n\n" + ORCHESTRATOR_DELEGATION,
        tools=[
            AgentTool(agent=inventory_agent),          # worker: products
            AgentTool(agent=order_agent),              # worker: order status
            AgentTool(agent=checkout_agent),           # worker: place an order
            AgentTool(agent=order_management_agent),   # worker: fulfillment pipeline
        ],
    )
    return orchestrator


# --------------------------------------------------------------------------- #
# Agent service (the single entry point used by the API)
# --------------------------------------------------------------------------- #
class AgentService:
    def __init__(self):
        self.memory = get_memory_store()
        self._harness = None   # COMMON AgentHarness wrapping the ADK root agent
        self._adk_ready = False
        self._openai = None   # active LLM client (OpenAI)
        self._gemini = None   # kept for future use (see commented init below)
        self._last_checkout = None  # structured checkout result for the last turn
        self._init_backends()

    def _init_backends(self) -> None:
        """
        Best-effort init of the LLM backends used for a conversational turn.

        Provider selection (settings.llm_provider):
          * "openai" (default) — phrasing via OpenAI; ADK path stays off.
          * "gemini"           — enables the Google ADK multi-agent orchestrator
                                  (produces ADK traces) and a raw Gemini phrasing
                                  client. Use Vertex AI (GOOGLE_GENAI_USE_VERTEXAI
                                  =true) to get the $300-credit / high quota
                                  instead of the 20/day AI Studio free tier.
        Both inits are guarded so a missing key/package degrades gracefully to the
        deterministic template path rather than crashing.
        """
        provider = _settings.llm_provider.lower()

        # --- OpenAI client (used when llm_provider == "openai") ---
        if provider == "openai" and _settings.openai_api_key:
            try:
                from openai import OpenAI

                kwargs = {"api_key": _settings.openai_api_key}
                if _settings.openai_base_url:
                    kwargs["base_url"] = _settings.openai_base_url
                self._openai = OpenAI(**kwargs)
                log_event("orchestrator_init", path="openai",
                          model=_settings.openai_model)
            except Exception as exc:
                log_event("openai_unavailable", reason=str(exc))

        # --- GEMINI / ADK (used when llm_provider == "gemini") ---
        # Re-enabled per request so the ADK multi-agent orchestrator runs and
        # emits ADK traces. Point at Vertex AI to use the $300 credit / higher
        # Gemini quota (see .env: GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT).
        if provider == "gemini":
            # ADK multi-agent path — built when use_adk_path on. The root agent
            # runs through the COMMON AgentHarness (same scaffolding the advisor
            # uses); ready() builds it once and degrades gracefully if ADK is
            # absent (caller then uses the deterministic engine).
            if _settings.use_adk_path:
                from .harness import AgentHarness

                self._harness = AgentHarness(
                    name="orchestrator", app_name="goopher",
                    build_agent=build_root_agent,
                )
                self._adk_ready = self._harness.ready()
                if self._adk_ready:
                    log_event("orchestrator_init", path="adk",
                              model=_settings.gemini_model)

            # Raw Gemini client for the grounded phrasing path / fallback.
            if _settings.google_api_key or _settings.use_vertexai:
                try:
                    import google.generativeai as genai

                    if _settings.google_api_key:
                        genai.configure(api_key=_settings.google_api_key)
                    self._gemini = genai.GenerativeModel(_settings.gemini_model)
                    log_event("gemini_init", model=_settings.gemini_model)
                except Exception as exc:
                    log_event("gemini_unavailable", reason=str(exc))

    # ----- public API ----- #
    def run_turn(self, req: ChatRequest, customer_id: str) -> ChatResponse:
        """
        Process one conversational turn end-to-end, preserving context across
        channel/language/modality switches via shared session memory.
        """
        import time as _time

        incr("chat_requests_total")
        self._last_checkout = None  # reset per turn; set only on a checkout turn
        # Dev-portal flow capture for this turn (full end-to-end pipeline).
        ft = TurnTrace(kind="turn")
        ft.record.session_id = req.session_id
        ft.record.customer_id = customer_id
        ft.record.user_message = req.message

        # Worker + specialist sub-agents the orchestrator delegates to (they come
        # back in `used_tools` from the ADK run). Worker agents OWN the tools, so
        # a worker name in used_tools means the orchestrator delegated to it; the
        # actual tool names appear too (the worker called them).
        # Worker sub-agents the orchestrator delegates to (the rest is the tools
        # those workers call). modality/language/channel are deterministic
        # pre-processing now, not sub-agents.
        SUBAGENT_NAMES = {"inventory_agent", "order_agent", "checkout_agent",
                          "order_management_agent"}
        # Which agent skill (registry) each worker sub-agent picks — surfaced in
        # the dev portal so the pipeline reads agent → skill → tools.
        SUBAGENT_SKILL = {"inventory_agent": "inventory", "order_agent": "order",
                          "checkout_agent": "checkout",
                          "order_management_agent": "fulfillment"}

        with span("chat_turn", session=req.session_id, channel=req.channel,
                  customer=customer_id) as trace_id:
            ft.record.trace_id = trace_id
            ft.step("auth", "JWT verified", f"customer={customer_id}")
            ft.step("session", "memory.get",
                    f"session_id={req.session_id} (backend={_settings.db_backend})")

            import time as _time

            with span("session.memory_get", backend=_settings.db_backend):
                mem = self.memory.get(req.session_id, customer_id)

            # --- PHASE 1: deterministic pre-processing (fast Python, no LLM) ---
            # modality / language / channel / memory are handled here reliably —
            # NOT as ADK sub-agents. They're still wrapped in lightweight trace
            # spans so they ALSO appear in Cloud Trace (not just the dev portal),
            # while staying plain, instant, no-LLM Python.
            _t0 = _time.perf_counter()
            with span("preprocess.modality_agent"):
                modality = modality_agent.classify_modality(req.message, req.attachments)
                if getattr(req, "voice", False) and modality == "text":
                    modality = "voice"
                text = modality_agent.normalize_to_text(
                    req.message, req.attachments, _settings.gemini_model
                )
            ft.step("preprocess", "modality_agent",
                    f"modality={modality}", ms=(_time.perf_counter() - _t0) * 1000,
                    modality=modality)

            with span("preprocess.language_agent"):
                language = req.language or language_agent.detect_language(
                    text, default=self.memory.recall(req.session_id, "language", "en")
                )
                self.memory.remember(req.session_id, "language", language)
            ft.step("preprocess", "language_agent", f"language={language}",
                    language=language)

            with span("preprocess.channel_agent", channel=req.channel):
                channel = req.channel
                self.memory.remember(req.session_id, "channel", channel)
            ft.step("preprocess", "channel_agent", f"channel={channel}", channel=channel)

            self.memory.add_turn(
                req.session_id,
                Turn(role="user", content=text, channel=channel,
                     language=language, modality=modality),
            )

            # --- PHASE 2: the ADK ORCHESTRATOR delegates to a WORKER sub-agent ---
            directives = (
                channel_agent.channel_directive(channel) + "\n"
                + language_agent.language_directive(language)
                + f"\nThe signed-in customer_id is {customer_id}."
            )
            # RSI: retrieve lessons the CriticAgent learned from past feedback and
            # inject them as guidance for the LLM paths only. Purely ADDITIVE and
            # guarded — never changes routing/checkout, and a no-op when nothing
            # matches, so existing behaviour is unchanged unless a lesson applies.
            _rsi_lessons = []
            try:
                from .critic_agent import get_critic
                _rsi_lessons = get_critic().retrieve_lessons(text, k=3, language=language)
            except Exception as exc:  # noqa: BLE001 - RSI must never break a turn
                log_event("rsi_retrieve_skipped", reason=str(exc))
            _rsi_guidance = ""
            if _rsi_lessons:
                _rsi_guidance = "\n".join(f"- {L.get('lesson', '')}" for L in _rsi_lessons)
                directives += ("\n\nLEARNED LESSONS (you MUST apply these corrective "
                               "instructions from past customer feedback):\n" + _rsi_guidance
                               + "\nIf the customer asks for something we don't sell, "
                               "do NOT just decline — briefly say we don't carry it, then "
                               "name 2-3 SPECIFIC in-stock products from the list below as "
                               "alternatives and ask one clarifying question."
                               + self._instock_highlights())
            # CHECKOUT is transactional → always handle it deterministically with
            # structured output (cart + staged receipt + the checkout payload the
            # extension needs), regardless of whether the ADK path is on. Leaving
            # a purchase to free-form ADK/LLM phrasing drops the cart and the
            # structured fields, which is exactly what was happening in the cloud.
            # An uploaded order FILE ("order these items") → structured bulk order
            # from the file's contents. Checked first since the file content (not
            # the chat text) holds the items. Falls back to normal checkout.
            checkout = (self._try_file_bulk_order(req.message, req.attachments, customer_id)
                        or self._try_checkout(text, customer_id, confirm=req.confirm))
            # RSI hand-off: if the gate couldn't RESOLVE the item (a "we don't carry
            # X" refusal) AND a learned lesson applies, don't return the bare
            # deterministic refusal — fall through to the LLM/fallback path so the
            # lesson is applied (acknowledge → suggest in-stock alternatives → ask).
            # Never for a resolved cart or a bulk/file order, and still never
            # substitutes (the item simply isn't in the catalog).
            _rsi_handoff = False
            if (checkout is not None and _rsi_lessons
                    and isinstance(self._last_checkout, dict)
                    and self._last_checkout.get("ok") is False
                    and not self._last_checkout.get("bulk")):
                log_event("rsi_checkout_handoff", q=text[:80], lessons=len(_rsi_lessons))
                self._last_checkout = None
                checkout = None
                _rsi_handoff = True
            if checkout is not None:
                reply, used_tools = checkout
                # Checkout is the DETERMINISTIC transactional gate — NOT an LLM/ADK
                # agent run, so there's no harness here (that's the point: "LLM
                # orchestrates, code transacts"). We still surface the checkout
                # SKILL + its tools so the path has skill/tool parity with ADK.
                ft.step("orchestrator", "checkout — DETERMINISTIC transactional gate",
                        "the gate transacts (cart → payment → ORDER_PLACED); the "
                        "LLM never executes the purchase")
                for name in used_tools:
                    if name in SUBAGENT_NAMES:
                        ft.step("subagent", f"↳ {name}",
                                "checkout worker (structured, deterministic)", tool=name)
                        sk_name = SUBAGENT_SKILL.get(name)
                        if sk_name:
                            sk = skills.get_skill(sk_name)
                            ft.step("skill", f"   ↳ skill: {sk.name}",
                                    f"{sk.title} — "
                                    f"{'read-only' if sk.read_only else 'transactional'}"
                                    f" · tools: {', '.join(sk.tool_names())}",
                                    skill=sk.name, read_only=sk.read_only)
                    else:
                        ft.step("tool", f"↳ {name}",
                                "checkout tool (deterministic gate)", tool=name)
                # Order-confirmation email (best-effort notification) — surface it
                # as its own pipeline log line so the portal shows it was sent.
                _em = (self._last_checkout or {}).get("email") if self._last_checkout else None
                if _em and _em.get("to"):
                    if _em.get("sent"):
                        ft.step("email", "✅ order email sent",
                                f"confirmation emailed to {_em['to']} via {_em.get('mode')}",
                                to=_em["to"], mode=_em.get("mode"))
                    else:
                        ft.step("email", "📧 order email (not sent)",
                                f"{_em['to']} — {_em.get('mode')}"
                                + (f": {_em.get('detail')}" if _em.get("detail") else ""),
                                to=_em["to"], mode=_em.get("mode"))
                path = "checkout"
            elif self._adk_ready and _settings.use_adk_path:
                try:
                    _t0 = _time.perf_counter()
                    reply, used_tools = self._generate_adk(
                        req.session_id, text, customer_id, directives)
                    # The orchestrator runs through the COMMON AgentHarness — show
                    # that scaffolding layer explicitly in the pipeline.
                    ft.step("harness", "AgentHarness · orchestrator",
                            "common scaffolding: build → session → run-loop → "
                            "collect (text/tool-calls) → resilience → result",
                            app="goopher", model=_settings.gemini_model)
                    ft.step("orchestrator",
                            "invoke_agent: goopher_orchestrator (ADK + gemini)",
                            "ROOT agent — selected a worker sub-agent and composed "
                            "the reply", ms=(_time.perf_counter() - _t0) * 1000)
                    for name in used_tools:
                        if name in SUBAGENT_NAMES:
                            ft.step("subagent", f"↳ {name}",
                                    "worker sub-agent invoked by orchestrator", tool=name)
                            # The skill (registry capability) that worker picked.
                            sk_name = SUBAGENT_SKILL.get(name)
                            if sk_name:
                                sk = skills.get_skill(sk_name)
                                ft.step("skill", f"   ↳ skill: {sk.name}",
                                        f"{sk.title} — "
                                        f"{'read-only' if sk.read_only else 'transactional'}"
                                        f" · tools: {', '.join(sk.tool_names())}",
                                        skill=sk.name, read_only=sk.read_only)
                        else:
                            ft.step("tool", f"↳ {name}",
                                    "tool called by the worker sub-agent", tool=name)
                    path = "adk"
                except Exception as exc:
                    log_event("adk_turn_failed", reason=str(exc))
                    incr("errors_total")
                    ft.step("orchestrator", "ADK orchestrator FAILED → backup",
                            f"{type(exc).__name__}: {str(exc)[:200]}")
                    reply, used_tools = self._generate_fallback(
                        req.session_id, text, customer_id, directives, channel, language,
                        skip_checkout=_rsi_handoff)
                    path = "fallback"
            else:
                ft.step("orchestrator", f"deterministic router ({_settings.llm_provider})",
                        "BACKUP engine — intent routing + grounded reply")
                reply, used_tools = self._generate_fallback(
                    req.session_id, text, customer_id, directives, channel, language,
                    skip_checkout=_rsi_handoff)
                for name in used_tools:
                    ft.step("tool", name, "tool executed (backup)", tool=name)
                path = "fallback"

            # Surface RSI in the reply meta + /dev when a learned lesson shaped an
            # LLM answer (not the deterministic checkout path).
            if _rsi_lessons and path in ("adk", "fallback"):
                used_tools = list(used_tools) + ["lesson_retrieve"]
                ft.step("rsi", f"💡 lesson_retrieve — applied {len(_rsi_lessons)} learned lesson(s)",
                        _rsi_guidance[:180])

            if channel == "phone":
                with span("preprocess.adapt_for_phone"):
                    reply = channel_agent.adapt_for_phone(reply)
                ft.step("preprocess", "adapt_for_phone", "voice-safe text")

            with span("memory.session_update", backend=_settings.db_backend):
                self.memory.add_turn(
                    req.session_id,
                    Turn(role="assistant", content=reply, channel=channel,
                         language=language, modality=modality),
                )

            # (User + assistant turns are persisted inside the path helpers.)
            ft.step("memory", "session updated",
                    "persisted user + assistant turns to session memory")

            log_event("chat_reply", session=req.session_id, language=language,
                      channel=channel, modality=modality, used_tools=used_tools,
                      trace_id=trace_id)

            # Commit the captured flow for the dev portal.
            ft.record.channel = channel
            ft.record.language = language
            ft.record.modality = modality
            ft.record.reply = reply
            ft.record.used_tools = used_tools
            try:
                ft.record.memory = {
                    "history_preview": self.memory.history_text(req.session_id, limit=6),
                    "language": self.memory.recall(req.session_id, "language"),
                    "channel": self.memory.recall(req.session_id, "channel"),
                }
            except Exception:
                pass
            ft.commit()

            return ChatResponse(
                reply=reply, session_id=req.session_id, language=language,
                channel=channel, used_tools=used_tools, trace_id=trace_id,
                checkout=self._last_checkout,
            )

    @staticmethod
    def _instock_highlights(n: int = 6) -> str:
        """A few real in-stock products (Toys first) the agent can suggest as
        concrete alternatives when a learned lesson applies. Cheap & cached-ish;
        never raises."""
        try:
            from ..db.database import get_repository
            prods = [p for p in get_repository().list_products()
                     if any(v.stock > 0 for v in p.variants)]
            # surface Toys first (most useful as a gift/tech alternative), then the rest
            prods.sort(key=lambda p: 0 if (p.department or "").lower().startswith("toy") else 1)
            items = [f"{p.name} (${p.sale_price:.2f}, {p.department})" for p in prods[:n]]
            return ("\nIN-STOCK ITEMS you may suggest as alternatives: "
                    + "; ".join(items) + ".") if items else ""
        except Exception:  # noqa: BLE001
            return ""

    # ----- generation paths (called by run_turn after pre-processing) ----- #
    def _generate_adk(self, session_id: str, text: str, customer_id: str,
                      directives: str) -> tuple[str, list[str]]:
        """
        Run the turn through the COMMON AgentHarness (the same scaffolding the
        advisor uses): it ensures the ADK session exists, streams the turn, and
        collects the text + tool calls. We prefer the final response, fall back to
        the last text, and raise if ADK produced nothing — so the caller falls
        back to the deterministic engine rather than returning an empty apology.
        """
        history = self.memory.history_text(session_id)
        prompt = f"{directives}\n\nConversation so far:\n{history}\n\nUser: {text}"

        result = self._harness.run(
            user_id=customer_id, session_id=session_id, prompt=prompt)
        # Prefer the final response; fall back to the last text any event emitted.
        reply = (result.final_text or result.last_text).strip()
        if not reply:
            raise RuntimeError("ADK produced no text response")
        return reply, result.used_tools

    @staticmethod
    def _resolve_id_to_variant(token: str):
        """Resolve a typed token to a concrete in-stock variant_id. Accepts a
        full variant_id OR a product SKU. Returns None if neither matches an
        in-stock item (caller must NOT substitute)."""
        from ..db.database import get_repository
        repo = get_repository()
        info = repo.check_stock(token)            # exact variant match?
        if info is not None:
            return token if info.get("in_stock") else None
        product = repo.get_product(token)         # product SKU? -> first in-stock variant
        if product is not None:
            for v in product.variants:
                if v.stock > 0:
                    return v.variant_id
        return None

    @staticmethod
    def _is_order_intent(lowered: str) -> bool:
        """True if the message is a PURCHASE intent (not an order-STATUS query).

        Catches natural phrasings the keyword list missed — "order balls for me",
        "can you order…", "get me a…", "i want to buy…" — while excluding
        tracking/status questions that merely contain the word "order".
        """
        import re
        # Status / tracking / post-order questions are NOT purchases.
        if re.search(r"ord-\d", lowered):
            return False
        if any(s in lowered for s in (
                "order status", "status of", "my order", "my orders", "track",
                "where is", "where's", "order history", "cancel", "return ",
                "did my", "has my", "is my order", "out for delivery")):
            return False
        # Explicit checkout phrases.
        if any(k in lowered for k in (
                "place an order", "place order", "checkout", "check out", "buy this",
                "buy it", "order this", "place my order", "complete my order",
                "order of", "order for")):
            return True
        # A purchase verb anywhere ("order balls", "buy a…", "purchase 2…",
        # "can you order…") or a polite request to get an item.
        if re.search(r"\b(order|buy|purchase)\b", lowered):
            return True
        if any(k in lowered for k in ("get me ", "grab me ", "i want ", "i'd like ",
                                      "i would like ", "wanna ")):
            return True
        return False

    @staticmethod
    def _parse_order_file(raw: str) -> list[tuple[str, int]]:
        """Parse an uploaded order file into [(product_query, qty), ...].

        Tolerant of common formats, one item per line:
          "2 soccer balls", "soccer ball x3", "3x oreos", "lego, 2",
          "TOY-SPL-3001", or just "oreos". CSV "item,qty" is handled too.
        """
        import re
        out: list[tuple[str, int]] = []
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip a leading action verb + separators so "order - 15 oreos" and
            # "buy: 2 lego" become "15 oreos" / "2 lego".
            line = re.sub(r"^(order|buy|purchase|add|get|want|need)\b[\s:_().\-]*",
                          "", line, flags=re.IGNORECASE).strip()
            if not line:
                continue
            qty, item = 1, line
            m = re.match(r"^(\d{1,4})\s*[xX]\s+(.+)$", line)        # "3x item"
            if m:
                qty, item = int(m.group(1)), m.group(2)
            elif re.match(r"^\d{1,4}\s+\S", line):                  # "15 item"
                m = re.match(r"^(\d{1,4})\s+(.+)$", line)
                qty, item = int(m.group(1)), m.group(2)
            else:                                                   # "item x3" / "item, 3"
                m = re.match(r"^(.+?)[\s,]+[xX]?(\d{1,4})$", line)
                if m:
                    item, qty = m.group(1), int(m.group(2))
            item = item.strip(" ,:-\t")
            if item:
                out.append((item, max(1, min(qty, 500))))
        return out

    @staticmethod
    def _parse_tabular(rows) -> list[tuple[str, str, int]]:
        """Parse a SPREADSHEET/CSV order (xlsx or csv) into [(name, sku, qty), ...].

        `rows` is a list of row tuples; the first row is the header. We locate the
        product-name, SKU, and quantity columns by header name (tolerant of case,
        spaces, underscores). Returns [] if it isn't a recognizable order table —
        so a plain-text .txt file falls back to the line parser."""
        import re
        rows = [r for r in (rows or []) if r is not None]
        if not rows:
            return []
        norm = lambda c: re.sub(r"[^a-z0-9]+", "_", str(c if c is not None else "").strip().lower()).strip("_")
        header = [norm(c) for c in rows[0]]
        find = lambda cands: next((i for i, h in enumerate(header) if h in cands), -1)
        qty_i = find({"order_quantity", "quantity", "qty", "units", "order_qty", "count"})
        sku_i = find({"sku", "product_sku", "item_sku", "variant_id", "product_code"})
        name_i = find({"product_name", "product", "item", "item_name", "name",
                       "description", "product_description"})
        if name_i < 0 and sku_i < 0:
            return []                              # not an order table → caller falls back
        cell = lambda r, i: ("" if not (0 <= i < len(r)) or r[i] is None else str(r[i]).strip())
        out: list[tuple[str, str, int]] = []
        for r in rows[1:]:
            name, sku = cell(r, name_i), cell(r, sku_i)
            if not name and not sku:
                continue
            qty = 1
            if qty_i >= 0:
                try:
                    qty = int(float(cell(r, qty_i) or 1))
                except Exception:  # noqa: BLE001
                    qty = 1
            out.append((name, sku, max(1, min(qty, 999))))
        return out

    def _resolve_order_line(self, query: str):
        """Resolve one order-file line to (variant_id, product_name) or None.
        Accepts a SKU/variant token or a free-text product name; never substitutes."""
        import re
        from ..tools.checkout_tool import resolve_variant_by_name
        token = query.strip()
        if re.match(r"(?i)^(JCP|FOOD|TOY)-[A-Z0-9\-]+$", token):
            vid = self._resolve_id_to_variant(token.upper())
            if vid:
                from ..db.database import get_repository
                info = get_repository().check_stock(vid)
                return vid, (info["product"] if info else token)
            return None
        res = resolve_variant_by_name(token)
        return (res["variant_id"], res["product"]) if res.get("ok") else None

    def _try_file_bulk_order(self, message: str, attachments, customer_id: str):
        """If the customer attached a file AND asked to order it, parse the file
        and place a structured BULK order for the items it lists. Returns
        (reply, used_tools) or None when it doesn't apply."""
        import base64
        from ..tools.checkout_tool import place_bulk_order

        atts = attachments or []
        file_att = next((a for a in atts
                         if getattr(a, "kind", "") == "file" and getattr(a, "content_b64", None)),
                        None)
        if file_att is None:
            return None
        low = (message or "").lower()
        # Only act on an order-ish request (or a bare "order this file").
        if not (self._is_order_intent(low) or "order" in low or "checkout" in low):
            return None
        try:
            raw_bytes = base64.b64decode(file_att.content_b64)
        except Exception:
            return None
        fname = (getattr(file_att, "filename", "") or "").lower()
        mime = (getattr(file_att, "mime_type", "") or "").lower()

        # Parse the file into (name, sku, qty) triples — supporting Excel (.xlsx),
        # CSV (with headers), and plain text. An .xlsx is a binary ZIP, so it must
        # be parsed with openpyxl, NOT decoded as text (that returned garbage →
        # empty → the default basket).
        triples: list[tuple[str, str, int]] = []
        is_xlsx = raw_bytes[:2] == b"PK" or fname.endswith(".xlsx") or "spreadsheet" in mime or "excel" in mime
        if is_xlsx:
            try:
                import io
                import openpyxl  # lazy
                wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
                rows = list(wb.active.iter_rows(values_only=True))
                triples = self._parse_tabular(rows)
            except Exception as exc:  # noqa: BLE001
                log_event("xlsx_parse_failed", reason=str(exc))
                return None
        else:
            text = raw_bytes.decode("utf-8", errors="ignore")
            if fname.endswith(".csv") or "csv" in mime or ("," in text and "," in (text.splitlines() or [""])[0]):
                import csv
                import io
                triples = self._parse_tabular(list(csv.reader(io.StringIO(text))))
            if not triples:  # plain-text order list (one item/line)
                triples = [(item, "", qty) for (item, qty) in self._parse_order_file(text)]
        if not triples:
            return None

        variant_ids, quantities, names, not_found = [], [], [], []
        for name, sku, qty in triples:
            hit = (self._resolve_order_line(sku) if sku else None) or \
                  (self._resolve_order_line(name) if name else None)
            if hit:
                variant_ids.append(hit[0]); quantities.append(qty); names.append(hit[1])
            else:
                not_found.append(name or sku)

        if not variant_ids:
            msg = ("I read your file but couldn't match any of its items to the "
                   f"catalog: {', '.join(not_found[:10])}. No order was placed.")
            self._last_checkout = self._checkout_payload({"ok": False, "message": msg}, bulk=True)
            return msg, ["checkout_agent"]

        # PREVIEW first (no charge) and ask the shopper to confirm — same as the
        # text/voice/camera flow. The Confirm button re-sends `confirm_text` (the
        # resolved SKUs + quantities) so the file never needs re-uploading.
        spec = {"ok": True, "variant_ids": variant_ids, "quantities": quantities, "bulk": True}
        self._last_checkout = self._preview_payload(spec)
        self._last_checkout["confirm_text"] = "__bulk_confirm__ " + "; ".join(
            f"{v}={q}" for v, q in zip(variant_ids, quantities))
        reply = self._format_preview(self._last_checkout)
        if not_found:
            reply += ("\n\n⚠️ Not found in the catalog (skipped, not substituted): "
                      + ", ".join(not_found[:10]))
        return reply, ["checkout_agent"]

    def _try_checkout(self, text: str, customer_id: str, confirm: bool = False):
        """
        Handle checkout intents ("place an order" / bulk) DETERMINISTICALLY.

        TWO-STEP by default: it RESOLVES the item(s) and, unless `confirm=True`,
        returns a CART PREVIEW asking the shopper to confirm — it does NOT charge
        or place anything yet. When the shopper confirms (the extension re-sends
        the same request with confirm=True), it actually places the order and
        returns the staged receipt. Sets self._last_checkout (cart + payload the
        extension UI needs). Returns (reply, used_tools) or None if not a checkout.
        """
        import re
        from ..tools.checkout_tool import place_bulk_order, place_order

        lowered = text.lower()
        spec = self._resolve_order(text, lowered, customer_id)
        if spec is None:
            return None                      # not a checkout intent
        if not spec.get("ok"):               # couldn't resolve → refuse, no substitution
            self._last_checkout = self._checkout_payload(
                {"ok": False, "message": spec["message"]}, bulk=spec.get("bulk", False))
            return spec["message"], ["checkout_agent"]

        bulk = spec["bulk"]
        # STEP 1 — preview + ask to confirm (no charge yet).
        if not confirm:
            self._last_checkout = self._preview_payload(spec)
            return self._format_preview(self._last_checkout), ["checkout_agent"]

        # STEP 2 — confirmed → actually place the order.
        vids, qtys = spec["variant_ids"], spec["quantities"]
        if bulk or len(vids) > 1:
            data = place_bulk_order(customer_id, variant_ids=vids, quantities=qtys)
        else:
            data = place_order(customer_id, variant_id=vids[0], qty=qtys[0])
        self._last_checkout = self._checkout_payload(data, bulk=bulk)
        return (self._format_bulk_checkout(data) if bulk
                else self._format_checkout(data)), ["checkout_agent"]

    def _resolve_order(self, text: str, lowered: str, customer_id: str):
        """Resolve a checkout intent to a spec {ok, variant_ids, quantities, bulk}
        WITHOUT placing anything. Returns None if `text` isn't a checkout intent,
        or {ok: False, message, bulk} if it can't be fulfilled (never substitutes)."""
        import re
        from ..tools.checkout_tool import resolve_variant_by_name

        # CONFIRM re-send for a file/CSV/xlsx bulk order: the Confirm button sends
        # "__bulk_confirm__ SKU=qty; SKU=qty; …" so the order is placed WITHOUT
        # re-uploading the file. Parse those exact lines (never substitute).
        if text.strip().startswith("__bulk_confirm__"):
            vids, qtys = [], []
            for sku, q in re.findall(r"([A-Z0-9][A-Z0-9\-]+)\s*=\s*(\d+)", text):
                vid = self._resolve_id_to_variant(sku)
                if vid:
                    vids.append(vid); qtys.append(int(q))
            if vids:
                return {"ok": True, "variant_ids": vids, "quantities": qtys, "bulk": True}
            return {"ok": False, "bulk": True,
                    "message": "The previewed items are no longer in stock — nothing was placed."}

        variant_ids = re.findall(r"JCP-[A-Z0-9\-]+|FOOD-[A-Z0-9\-]+|TOY-[A-Z0-9\-]+",
                                 text.upper())
        qty = self._extract_qty(text)
        bulk_intent = any(k in lowered for k in (
            "bulk order", "place bulk", "order multiple", "buy several",
            "buy multiple", "order several", "multiple items", "many items"))

        # --- BULK ---
        if bulk_intent:
            if variant_ids:
                vids = [self._resolve_id_to_variant(v) for v in variant_ids]
                vids = [v for v in vids if v]
                if vids:
                    return {"ok": True, "variant_ids": vids,
                            "quantities": [max(qty, 1)] * len(vids), "bulk": True}
            else:
                product = self._extract_order_product(text)
                if product:
                    res = resolve_variant_by_name(product)
                    if not res.get("ok"):
                        return {"ok": False, "message": res["message"], "bulk": True}
                    return {"ok": True, "variant_ids": [res["variant_id"]],
                            "quantities": [max(qty, 10)], "bulk": True}  # "bulk" ⇒ ≥10
            # bare "place a bulk order" → a representative default basket
            vids = self._default_basket(3)
            return {"ok": True, "variant_ids": vids,
                    "quantities": [max(qty, 1)] * len(vids), "bulk": True}

        # --- SINGLE ---
        if not self._is_order_intent(lowered):
            return None
        if variant_ids:
            vid = self._resolve_id_to_variant(variant_ids[0])
            if vid is None:
                return {"ok": False, "bulk": False,
                        "message": f'Sorry, "{variant_ids[0]}" isn\'t available, so '
                                   f'nothing was ordered and nothing was substituted.'}
            return {"ok": True, "variant_ids": [vid], "quantities": [qty], "bulk": False}

        product = self._extract_order_product(text)
        contextual = bool(re.search(
            r"\b(above|this|that|these|those|them|it|same|last|previous|the one)\b", lowered))
        if product:
            res = resolve_variant_by_name(product)
            if not res.get("ok"):
                return {"ok": False, "message": res["message"], "bulk": False}
            return {"ok": True, "variant_ids": [res["variant_id"]], "quantities": [qty], "bulk": False}
        if contextual:
            from ..tools.inventory_tool import get_last_viewed
            lv = get_last_viewed()
            vid = self._resolve_id_to_variant(lv["sku"]) if lv else None
            if vid is None:
                return {"ok": False, "bulk": False,
                        "message": "Which item would you like to order? Tell me the "
                                   "product name, or ask me about it first."}
            return {"ok": True, "variant_ids": [vid], "quantities": [qty], "bulk": False}
        # bare "place an order" → default demo item
        vids = self._default_basket(1)
        if not vids:
            return {"ok": False, "bulk": False, "message": "No in-stock items available."}
        return {"ok": True, "variant_ids": vids, "quantities": [qty], "bulk": False}

    @staticmethod
    def _default_basket(n: int) -> list[str]:
        """First `n` in-stock variants (one per product) — for bare bulk/order demos."""
        from ..db.database import get_repository
        repo = get_repository()
        out = []
        for p in repo.list_products():
            for v in p.variants:
                if v.stock > 0:
                    out.append(v.variant_id)
                    break
            if len(out) >= n:
                break
        return out

    def _preview_payload(self, spec: dict) -> dict:
        """Build a PENDING cart preview from a resolved spec — no order placed."""
        from ..db.database import get_repository
        repo = get_repository()
        cart, total = [], 0.0
        for vid, q in zip(spec["variant_ids"], spec["quantities"]):
            info = repo.check_stock(vid)
            if not info:
                continue
            line_total = round(info["sale_price"] * q, 2)
            total += line_total
            cart.append({"name": info["product"], "color": info["color"],
                         "size": info["size"], "qty": q,
                         "unit_price": info["sale_price"], "line_total": line_total})
        total = round(total, 2)
        return {"ok": True, "pending": True, "bulk": spec["bulk"], "cart": cart,
                "items": [f'{c["name"]} ({c["color"]}, {c["size"]}) x{c["qty"]}' for c in cart],
                "subtotal": total, "total": total}

    @staticmethod
    def _format_preview(payload: dict) -> str:
        """Reply shown for STEP 1: the cart + an explicit confirm question."""
        return (AgentService._cart_block(payload)
                + "\n\n🟡 Please confirm — should I place this order?")

    def _generate_fallback(self, session_id: str, text: str, customer_id: str,
                           directives: str, channel: str, language: str,
                           skip_checkout: bool = False
                           ) -> tuple[str, list[str]]:
        """
        Deterministic engine: route intent -> call the real tools -> phrase the
        answer (via Gemini if available, else a clean template). This keeps the
        service fully functional with no ADK and is what unit tests exercise.

        `skip_checkout=True` is used on an RSI hand-off: the gate already failed to
        resolve the item and a learned lesson applies, so we DON'T re-run checkout
        (it would just re-emit the same refusal) — we let the search + lesson-aware
        phrasing suggest in-stock alternatives instead.
        """
        from ..tools.inventory_tool import check_stock, search_inventory
        from ..tools.order_tool import bulk_order_status, get_order_status, list_customer_orders

        import re
        used_tools: list[str] = []
        lowered = text.lower()

        # Checkout is transactional → always handled by the shared structured
        # handler (works for both the ADK and deterministic paths).
        if not skip_checkout:
            checkout = self._try_checkout(text, customer_id)
            if checkout is not None:
                return checkout

        # --- intent: bulk orders (high volume) ---
        order_ids = modality_agent.extract_order_ids_from_text(text)
        if len(order_ids) > 1 or "all my order" in lowered and order_ids:
            data = bulk_order_status(order_ids)
            used_tools.append("order_bulk_status")
            facts = self._format_bulk(data)
        # --- intent: single order status ---
        elif order_ids:
            data = get_order_status(order_ids[0])
            used_tools.append("order_status")
            facts = self._format_order(data)
        # --- intent: list my orders ---
        elif any(k in lowered for k in ("my orders", "order history", "mis pedidos", "track my")):
            data = list_customer_orders(customer_id)
            used_tools.append("order_list_for_customer")
            facts = self._format_order_list(data)
        # --- intent: check specific variant stock ---
        elif "JCP-" in text.upper():
            import re
            vid = re.search(r"JCP-[A-Z0-9\-]+", text.upper())
            data = check_stock(vid.group(0)) if vid else {"found": False}
            used_tools.append("inventory_check_stock")
            facts = self._format_stock(data)
        # --- default intent: product search ---
        else:
            color, size, max_price = self._parse_filters(lowered)
            data = search_inventory(query=text, color=color, size=size, max_price=max_price)
            used_tools.append("inventory_search")
            facts = self._format_search(data)

        reply = self._phrase(text, facts, directives)
        return reply, used_tools

    # ----- phrasing & formatting helpers ----- #
    def _phrase(self, user_text: str, facts: str, directives: str) -> str:
        """
        Turn structured tool results into a natural reply using the active LLM.

        Uses OpenAI when llm_provider="openai", or Gemini when "gemini". The
        prompt grounds the model in the real tool output ("do not invent beyond
        this"), so the answer is always accurate. If the LLM is unavailable or
        errors, we fall back to the already-human-readable tool facts so the
        service never hard-fails.
        """
        system_prompt = f"{ROOT_INSTRUCTION}\n\n{directives}"
        user_prompt = (
            f"User asked: {user_text}\n\n"
            f"Tool results (ground truth — do not invent beyond this):\n{facts}\n\n"
            "Write a helpful, concise reply using only the tool results."
        )

        # --- OpenAI ---
        if self._openai is not None:
            try:
                incr("tokens_estimated_total", (len(system_prompt) + len(user_prompt)) // 4)
                resp = self._openai.chat.completions.create(
                    model=_settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=600,
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text
                log_event("openai_phrasing_empty")
            except Exception as exc:
                log_event("openai_phrasing_failed", reason=str(exc))

        # --- Gemini (used when llm_provider="gemini") ---
        if self._gemini is not None:
            try:
                prompt = f"{system_prompt}\n\n{user_prompt}"
                # gemini-2.5-* use "thinking" which eats output tokens; give a
                # generous budget so the visible answer isn't truncated to empty.
                resp = self._gemini.generate_content(
                    prompt, generation_config={"max_output_tokens": 2048}
                )
                text = self._extract_text(resp)
                if text:
                    return text
                log_event("gemini_phrasing_empty")
            except Exception as exc:
                log_event("gemini_phrasing_failed", reason=str(exc))

        # Template fallback (no LLM / on error): facts are already human-readable.
        return facts

    @staticmethod
    def _extract_text(resp) -> str:
        """Safely pull text out of a Gemini response (avoid resp.text accessor)."""
        try:
            parts = resp.candidates[0].content.parts or []
        except (AttributeError, IndexError):
            return ""
        return "".join(getattr(p, "text", "") or "" for p in parts).strip()

    @staticmethod
    def _parse_filters(lowered: str):
        # Only clothing colors are treated as a color facet; food "flavors" are
        # matched through the free-text keyword search instead, so a query like
        # "barbecue chips" still works without a hard-coded flavor list.
        colors = ["black", "navy", "white", "sage", "emerald", "burgundy", "camel",
                  "olive", "ivory", "cream", "mustard", "terracotta", "charcoal"]
        sizes = ["xxl", "xl", "xs", "s", "m", "l"]
        color = next((c.title() for c in colors if c in lowered), "")
        size = next((s.upper() for s in sizes if f" {s} " in f" {lowered} "), "")
        max_price = None
        import re
        m = re.search(r"under \$?(\d+)", lowered)
        if m:
            max_price = float(m.group(1))
        return color, size, max_price

    @staticmethod
    def _format_search(data: dict) -> str:
        if not data.get("count"):
            return "No products matched that search."
        lines = [f"Found {data['count']} matching product(s):"]
        for p in data["products"][:5]:
            stock = sum(v["stock"] for v in p["in_stock_variants"])
            # "colors" doubles as flavors/variety for food items.
            options = ", ".join(p["colors"])
            lines.append(f"- {p['name']} by {p['brand']} — ${p['sale_price']:.2f} "
                         f"(was ${p['list_price']:.2f}), {stock} in stock, "
                         f"options: {options}")
        return "\n".join(lines)

    @staticmethod
    def _format_stock(data: dict) -> str:
        if not data.get("found"):
            return "I couldn't find that exact item in the catalog."
        status = "in stock" if data["in_stock"] else "out of stock"
        return (f"{data['product']} ({data['color']}, {data['size']}) is {status} "
                f"— {data['stock']} unit(s) at ${data['sale_price']:.2f}.")

    @staticmethod
    def _format_order(data: dict) -> str:
        if not data.get("found"):
            return data.get("message", "Order not found.")
        msg = f"Order {data['order_id']} is {data['status']}."
        if data.get("tracking_number"):
            msg += f" Carrier {data['carrier']}, tracking {data['tracking_number']}."
        if data.get("status") == "Delivered" and data.get("delivered_date"):
            msg += f" Delivered on {data['delivered_date']}."
        elif data.get("estimated_delivery"):
            msg += f" Estimated delivery {data['estimated_delivery']}."
        return msg

    @staticmethod
    def _format_order_list(data: dict) -> str:
        if not data.get("count"):
            return "You have no orders on file."
        lines = [f"You have {data['count']} order(s):"]
        for o in data["orders"]:
            lines.append(f"- {o['order_id']}: {o['status']} (${o['total']:.2f}, "
                         f"placed {o['order_date']})")
        return "\n".join(lines)

    @staticmethod
    def _format_bulk(data: dict) -> str:
        lines = [f"Processed {data['processed']} of {data['requested']} order(s): "
                 f"{data['found']} found, {len(data['missing'])} missing."]
        for o in data["orders"][:10]:
            lines.append(f"- {o['order_id']}: {o['status']} (est. "
                         f"{o.get('estimated_delivery', 'n/a')})")
        if data["missing"]:
            lines.append(f"Missing: {', '.join(data['missing'][:10])}")
        return "\n".join(lines)

    @staticmethod
    def _extract_qty(text: str) -> int:
        """Pull a small quantity from phrases like 'order 3 oreos'. Default 1."""
        import re
        for m in re.finditer(r"\b(\d{1,3})\b", text):
            n = int(m.group(1))
            if 1 <= n <= 100:
                return n
        return 1

    @staticmethod
    def _extract_order_product(text: str) -> str:
        """
        Extract the product a shopper wants to order from a natural phrase, e.g.
        'place an order of oreo cookies' -> 'oreo cookies'. Returns "" for a bare
        'place an order' (no product named) or a pronoun like 'this'/'it', which
        signals the caller to use the default-demo-item behavior instead.
        """
        import re
        low = text.strip().lower()
        # Drop modality placeholders the pipeline injects (e.g. "[file 'order.txt'
        # uploaded]", "[image ...]") so they're never mistaken for a product name.
        low = re.sub(r"\[[^\]]*\]", " ", low).strip()
        patterns = [
            r"place\s+(?:an?\s+)?(?:bulk\s+)?order\s+(?:of|for)\s+(.+)",
            r"order\s+(?:of|for)\s+(.+)",
            r"(?:i\s+(?:want|would like|wanna|need)\s+to\s+)?"
            r"(?:buy|purchase|order|get)\s+(?:me\s+|some\s+|an?\s+|the\s+)*(.+)",
        ]
        for pat in patterns:
            m = re.search(pat, low)
            if m:
                prod = m.group(1)
                prod = re.sub(r"\b\d{1,4}\b", " ", prod)  # drop quantities anywhere
                # Drop filler + contextual-reference words so they're never
                # mistaken for a product (e.g. "above 10 items" → "").
                prod = re.sub(
                    r"\b(please|now|thanks|thank you|today|asap|for me|for us|"
                    r"to me|right now|above|below|item|items|of|the|those|these|"
                    r"them|some|that|this|it|same|one|ones|last|previous|order)\b",
                    " ", prod)
                prod = re.sub(r"\s+", " ", prod).strip(" .,!?\"'")
                if prod in {"", "this", "it", "that", "one", "this item", "order"}:
                    return ""
                return prod
        return ""

    @staticmethod
    def _cart_block(data: dict) -> str:
        """A readable cart receipt from the structured cart lines."""
        cart = data.get("cart") or []
        lines = ["🛒 Your cart"]
        if cart:
            for it in cart:
                opt = ", ".join(x for x in (it.get("color"), it.get("size")) if x)
                opt = f" ({opt})" if opt else ""
                lines.append(
                    f"  • {it['name']}{opt} × {it['qty']}  —  "
                    f"${it['unit_price']:.2f} ea = ${it['line_total']:.2f}"
                )
        else:  # bulk/legacy: fall back to pre-formatted item strings
            for s in data.get("items", []):
                lines.append(f"  • {s}")
        sub = data.get("subtotal", data.get("total", 0.0))
        lines.append(f"  ──────────")
        lines.append(f"  Subtotal: ${sub:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _format_checkout(data: dict) -> str:
        if not data.get("ok"):
            return data.get("message", "Couldn't place the order right now.")
        pay = data.get("payment", {})
        out = [
            AgentService._cart_block(data),
            "💳 Processing payment…",
            f"✅ Payment {pay.get('status', 'SUCCESS')} "
            f"(txn {pay.get('transaction_id', '—')}) — ${data['total']:.2f} charged.",
            f"🎉 ORDER PLACED — {data['order_id']} · Status {data['status']} · "
            f"Est. delivery {data['estimated_delivery']}",
        ]
        fl = AgentService._fulfillment_line(data)
        if fl:
            out.append(fl)
        el = AgentService._email_line(data)
        if el:
            out.append(el)
        return "\n".join(out)

    @staticmethod
    def _email_line(data: dict) -> str:
        em = data.get("email") or {}
        to = em.get("to")
        if not to:
            return ""
        if em.get("sent"):
            return f"📧 Order confirmation emailed to {to}."
        if em.get("mode") == "simulated":
            return f"📧 Order confirmation queued for {to} (email simulated — set SMTP/Resend to send)."
        return f"📧 Confirmation for {to} could not be sent right now."

    @staticmethod
    def _checkout_payload(data: dict, bulk: bool) -> dict:
        """
        Structured checkout result for the extension's staged confirmation UI:
        payment success → "placement in progress" → "ORDER PLACED SUCCESSFULLY".
        """
        if not data.get("ok"):
            return {"ok": False, "message": data.get("message", "Checkout failed.")}
        pay = data.get("payment", {})
        f = data.get("fulfillment") or {}
        return {
            "ok": True,
            "bulk": bulk,
            "order_id": data.get("order_id"),
            "total": data.get("total"),
            "payment_status": pay.get("status", "SUCCESS"),
            "transaction_id": pay.get("transaction_id"),
            # True once the ORDER_PLACED insert happened (order management ran).
            "order_placed": bool(f.get("ok")),
            "tracking_number": f.get("tracking_number"),
            "inventory_ok": f.get("inventory_ok"),
            "estimated_delivery": data.get("estimated_delivery"),
            "items": data.get("items") or ([data["item"]] if data.get("item") else []),
            # Structured cart lines so the extension renders a real cart.
            "cart": data.get("cart", []),
            "subtotal": data.get("subtotal", data.get("total")),
            "email": data.get("email"),    # order-confirmation email status
        }

    @staticmethod
    def _fulfillment_line(data: dict) -> str:
        f = data.get("fulfillment") or {}
        if not f.get("ok"):
            return ""
        inv = "in stock ✓" if f.get("inventory_ok") else "low/out ⚠"
        return (f"📦 Order management: inventory {inv} · inserted into "
                f"ORDER_PLACED · shipped (UPS {f.get('tracking_number', '—')}) · "
                f"see the live pipeline in the dev portal.")

    @staticmethod
    def _format_bulk_checkout(data: dict) -> str:
        if not data.get("ok"):
            return data.get("message", "Couldn't place the bulk order right now.")
        pay = data.get("payment", {})
        out = [
            AgentService._cart_block(data),
            "💳 Processing payment…",
            f"✅ Payment {pay.get('status', 'SUCCESS')} "
            f"(txn {pay.get('transaction_id', '—')}) — ${data['total']:.2f} charged.",
            f"🎉 BULK ORDER PLACED — {data['order_id']} ({data['line_count']} items) · "
            f"Status {data['status']} · Est. delivery {data['estimated_delivery']}",
        ]
        fl = AgentService._fulfillment_line(data)
        if fl:
            out.append(fl)
        el = AgentService._email_line(data)
        if el:
            out.append(el)
        return "\n".join(out)


# Process-wide singleton.
_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _service
    if _service is None:
        _service = AgentService()
    return _service
