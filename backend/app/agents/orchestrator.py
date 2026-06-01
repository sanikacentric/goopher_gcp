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
from .skills import checkout_skill, inventory_skill, order_mgmt_skill, order_skill

_settings = get_settings()


ROOT_INSTRUCTION = """
You are GOOPHER, a friendly, efficient shopping assistant for an online store
with THREE departments: women's casual Clothing, Food/Snacks, and Toys. You help
customers discover products in ANY department, check live inventory, and manage
their orders (single or in bulk).

The store sells clothing (dresses), food/snacks (chips, cookies, soda, peanuts,
crackers, snack bars), AND toys (basketball, LEGO, NERF, Play-Doh, Hot Wheels,
puzzles). NEVER say you only sell one category.
Be concise and proactive. Surface low-stock warnings and the current sale price.
Stay on the topic of the store's clothing & food products and order help.
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
    # inventory_agent owns the inventory tools and calls them itself.
    inventory_agent = LlmAgent(
        name="inventory_agent",
        model=model,
        description="Specialist that answers product availability, price, and "
                    "stock questions by calling the inventory tools.",
        instruction=(
            "You are the inventory specialist for a store with women's casual "
            "Clothing and Food/Snacks. Use your tools to answer the request:\n"
            + inventory_skill.INSTRUCTION
            + "\nReturn the concrete results (names, prices, stock). Trust tool "
              "output; never claim the store only sells one category."
        ),
        tools=inventory_skill.get_tools(),
    )

    # order_agent owns the order tools and calls them itself.
    order_agent = LlmAgent(
        name="order_agent",
        model=model,
        description="Specialist that answers order-status and order-management "
                    "questions (single or bulk) by calling the order tools.",
        instruction=(
            "You are the order-management specialist. Use your tools to answer:\n"
            + order_skill.INSTRUCTION
            + "\nThe signed-in customer_id is provided in context; never ask for it."
        ),
        tools=order_skill.get_tools(),
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
            + checkout_skill.INSTRUCTION
            + "\nThe signed-in customer_id is provided in context; never ask for it."
        ),
        tools=checkout_skill.get_tools(),
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
            + order_mgmt_skill.INSTRUCTION
            + "\nThe signed-in customer_id is provided in context."
        ),
        tools=order_mgmt_skill.get_tools(),
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
        self._adk_runner = None
        self._adk_ready = False
        self._adk_sessions: set[str] = set()  # session_ids already created in ADK
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
            # ADK runner (Gemini multi-agent path) — built when use_adk_path on.
            if _settings.use_adk_path:
                try:
                    from google.adk.runners import InMemoryRunner

                    root = build_root_agent()
                    self._adk_runner = InMemoryRunner(agent=root, app_name="goopher")
                    self._adk_ready = True
                    log_event("orchestrator_init", path="adk",
                              model=_settings.gemini_model)
                except Exception as exc:
                    log_event("adk_unavailable", reason=str(exc))

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

        with span("chat_turn", session=req.session_id, channel=req.channel,
                  customer=customer_id) as trace_id:
            ft.record.trace_id = trace_id
            ft.step("auth", "JWT verified", f"customer={customer_id}")
            ft.step("session", "memory.get",
                    f"session_id={req.session_id} (backend={_settings.db_backend})")

            import time as _time

            mem = self.memory.get(req.session_id, customer_id)

            # --- PHASE 1: deterministic pre-processing (fast Python, no LLM) ---
            # modality / language / channel / memory are handled here reliably —
            # NOT as ADK sub-agents. Shown as "pre-process" in the portal.
            _t0 = _time.perf_counter()
            modality = modality_agent.classify_modality(req.message, req.attachments)
            if getattr(req, "voice", False) and modality == "text":
                modality = "voice"
            text = modality_agent.normalize_to_text(
                req.message, req.attachments, _settings.gemini_model
            )
            ft.step("preprocess", "modality_agent",
                    f"modality={modality}", ms=(_time.perf_counter() - _t0) * 1000,
                    modality=modality)

            language = req.language or language_agent.detect_language(
                text, default=self.memory.recall(req.session_id, "language", "en")
            )
            self.memory.remember(req.session_id, "language", language)
            ft.step("preprocess", "language_agent", f"language={language}",
                    language=language)

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
            # CHECKOUT is transactional → always handle it deterministically with
            # structured output (cart + staged receipt + the checkout payload the
            # extension needs), regardless of whether the ADK path is on. Leaving
            # a purchase to free-form ADK/LLM phrasing drops the cart and the
            # structured fields, which is exactly what was happening in the cloud.
            checkout = self._try_checkout(text, customer_id)
            if checkout is not None:
                reply, used_tools = checkout
                ft.step("orchestrator", "checkout (deterministic · structured)",
                        "placed order with cart + staged receipt")
                for name in used_tools:
                    ft.step("subagent", f"↳ {name}",
                            "checkout worker (structured)", tool=name)
                path = "checkout"
            elif self._adk_ready and _settings.use_adk_path:
                try:
                    _t0 = _time.perf_counter()
                    reply, used_tools = self._generate_adk(
                        req.session_id, text, customer_id, directives)
                    ft.step("orchestrator",
                            "invoke_agent: goopher_orchestrator (ADK + gemini)",
                            "ROOT agent — selected a worker sub-agent and composed "
                            "the reply", ms=(_time.perf_counter() - _t0) * 1000)
                    for name in used_tools:
                        if name in SUBAGENT_NAMES:
                            ft.step("subagent", f"↳ {name}",
                                    "worker sub-agent invoked by orchestrator", tool=name)
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
                        req.session_id, text, customer_id, directives, channel, language)
                    path = "fallback"
            else:
                ft.step("orchestrator", f"deterministic router ({_settings.llm_provider})",
                        "BACKUP engine — intent routing + grounded reply")
                reply, used_tools = self._generate_fallback(
                    req.session_id, text, customer_id, directives, channel, language)
                for name in used_tools:
                    ft.step("tool", name, "tool executed (backup)", tool=name)
                path = "fallback"

            if channel == "phone":
                reply = channel_agent.adapt_for_phone(reply)
                ft.step("preprocess", "adapt_for_phone", "voice-safe text")

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

    # ----- generation paths (called by run_turn after pre-processing) ----- #
    def _generate_adk(self, session_id: str, text: str, customer_id: str,
                      directives: str) -> tuple[str, list[str]]:
        """
        Run the turn through the ADK Runner.

        ADK's Runner requires a Session to exist before `run()` is called. The
        session-service API is async in current ADK, so we create the session
        (idempotently) via asyncio before streaming the turn. If ADK produces no
        text we raise, so the caller falls back to the deterministic engine
        rather than returning an empty apology.
        """
        import asyncio

        from google.genai import types  # ADK uses google-genai content types

        # Ensure the ADK session exists (create once per session_id).
        if session_id not in self._adk_sessions:
            try:
                asyncio.run(
                    self._adk_runner.session_service.create_session(
                        app_name="goopher", user_id=customer_id, session_id=session_id
                    )
                )
            except Exception as exc:
                # Already exists or transient — log and continue to run().
                log_event("adk_session_create_skipped", reason=str(exc))
            self._adk_sessions.add(session_id)

        history = self.memory.history_text(session_id)
        prompt = f"{directives}\n\nConversation so far:\n{history}\n\nUser: {text}"
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        used_tools: list[str] = []
        final_text = ""
        last_text = ""  # last non-empty text from ANY event (resilience fallback)
        for event in self._adk_runner.run(
            user_id=customer_id, session_id=session_id, new_message=content
        ):
            # Collect tool calls for observability, and the final text.
            if getattr(event, "get_function_calls", None):
                for fc in event.get_function_calls() or []:
                    used_tools.append(fc.name)
            if event.content and event.content.parts:
                txt = "".join(p.text or "" for p in event.content.parts)
                if txt.strip():
                    last_text = txt
                if getattr(event, "is_final_response", lambda: False)():
                    final_text = txt

        # Prefer the final response; if it was empty (e.g. a tool-only sub-agent
        # ended the stream), fall back to the last text the orchestrator emitted
        # before raising — only raise if there is genuinely nothing to return.
        reply = final_text.strip() or last_text.strip()
        if not reply:
            raise RuntimeError("ADK produced no text response")
        return reply, used_tools

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

    def _try_checkout(self, text: str, customer_id: str):
        """
        Handle checkout intents ("place an order" / bulk) DETERMINISTICALLY with
        structured output: it sets self._last_checkout (cart + staged payload for
        the extension UI) and returns a deterministic receipt as the reply.

        Used by BOTH the ADK and deterministic paths (called before either): a
        purchase is transactional and must be grounded and structured — never
        left to free-form LLM phrasing, which drops the cart and the fields the
        staged extension UI needs. Returns (reply, used_tools) or None if `text`
        is not a checkout intent.
        """
        import re
        from ..tools.checkout_tool import (place_bulk_order, place_order,
                                           resolve_variant_by_name)

        lowered = text.lower()
        # Accept clothing (JCP-), food (FOOD-) and toys (TOY-) SKUs.
        variant_ids = re.findall(r"JCP-[A-Z0-9\-]+|FOOD-[A-Z0-9\-]+|TOY-[A-Z0-9\-]+",
                                 text.upper())

        # --- PLACE A BULK ORDER (many items) — checked before single ---
        if any(k in lowered for k in ("bulk order", "place bulk", "order multiple",
                                      "buy several", "buy multiple", "order several",
                                      "multiple items", "many items")):
            data = place_bulk_order(customer_id, variant_ids=variant_ids or None, qty_each=1)
            self._last_checkout = self._checkout_payload(data, bulk=True)
            return self._format_bulk_checkout(data), ["checkout_agent"]

        # --- PLACE AN ORDER (single item) ---
        if any(k in lowered for k in ("place an order", "place order", "checkout",
                                      "check out", "buy this", "buy it", "order this",
                                      "place my order", "complete my order", "buy ",
                                      "purchase ", "order of", "order for")):
            qty = self._extract_qty(text)
            if variant_ids:
                # Explicit SKU/variant token in the message. It may be a full
                # variant_id OR a product SKU — resolve to a real in-stock
                # variant; refuse (no substitution) if it matches neither.
                vid = self._resolve_id_to_variant(variant_ids[0])
                if vid is None:
                    msg = (f'Sorry, "{variant_ids[0]}" isn\'t available, so no '
                           f'order was placed and nothing was substituted.')
                    self._last_checkout = self._checkout_payload(
                        {"ok": False, "message": msg}, bulk=False)
                    return msg, ["checkout_agent"]
                data = place_order(customer_id, variant_id=vid, qty=qty)
            else:
                # Did the shopper NAME a product (e.g. "place an order of oreo
                # cookies")? Resolve it by name and order THAT product. We must
                # never substitute a different item.
                product = self._extract_order_product(text)
                if product:
                    res = resolve_variant_by_name(product)
                    if not res.get("ok"):
                        # Not found / out of stock -> refuse cleanly, no substitution.
                        self._last_checkout = self._checkout_payload(
                            {"ok": False, "message": res["message"]}, bulk=False)
                        return res["message"], ["checkout_agent"]
                    data = place_order(customer_id, variant_id=res["variant_id"], qty=qty)
                else:
                    # Bare "place an order" with no product named -> default demo item.
                    data = place_order(customer_id, variant_id="", qty=qty)
            self._last_checkout = self._checkout_payload(data, bulk=False)
            # Deterministic receipt (NOT via LLM) so the cart + staged lines
            # always appear verbatim, in every path.
            return self._format_checkout(data), ["checkout_agent"]

        return None

    def _generate_fallback(self, session_id: str, text: str, customer_id: str,
                           directives: str, channel: str, language: str
                           ) -> tuple[str, list[str]]:
        """
        Deterministic engine: route intent -> call the real tools -> phrase the
        answer (via Gemini if available, else a clean template). This keeps the
        service fully functional with no ADK and is what unit tests exercise.
        """
        from ..tools.inventory_tool import check_stock, search_inventory
        from ..tools.order_tool import bulk_order_status, get_order_status, list_customer_orders

        import re
        used_tools: list[str] = []
        lowered = text.lower()

        # Checkout is transactional → always handled by the shared structured
        # handler (works for both the ADK and deterministic paths).
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
                prod = re.sub(r"^\d{1,3}\s+", "", prod)  # drop leading qty
                prod = re.sub(r"\b(please|now|thanks|thank you|today|asap)\b", "", prod)
                prod = prod.strip(" .,!?\"'")
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
        return "\n".join(out)

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
        return "\n".join(out)


# Process-wide singleton.
_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _service
    if _service is None:
        _service = AgentService()
    return _service
