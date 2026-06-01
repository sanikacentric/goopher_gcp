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
from .skills import inventory_skill, order_skill

_settings = get_settings()


ROOT_INSTRUCTION = """
You are GOOPHER, a friendly, efficient shopping assistant for an online store
with TWO departments: women's casual Clothing and Food/Snacks. You help
customers discover products in EITHER department, check live inventory, and
manage their orders (single or in bulk).

The store sells BOTH clothing (dresses) AND food/snacks (chips, cookies, soda,
peanuts, crackers, snack bars). NEVER say you only sell one category.
Be concise and proactive. Surface low-stock warnings and the current sale price.
Stay on the topic of the store's clothing & food products and order help.
""".strip()


# How the ROOT orchestrator must DELEGATE. It owns no retail tools itself — it
# picks a worker sub-agent for the task; the worker calls the tools.
ORCHESTRATOR_DELEGATION = """
You are GOOPHER, the MAIN orchestrator agent. You are in charge of the whole
turn and you coordinate your sub-agents (each is a tool you call), then compose
the final customer-facing reply.

Do this on EVERY turn, calling your sub-agents IN THIS ORDER:
1. `memory_agent`   — recall recent conversation context for this session.
2. `modality_agent` — classify the input (text/voice/image/file) → normalized text.
3. `language_agent` — detect the customer's language + localization directive.
4. Delegate to the WORKER sub-agent that fits the request, to get the real data:
     - product availability / price / stock / "do you have…" / "show me…"
       -> `inventory_agent` (owns the inventory tools)
     - order status / tracking / "where is my order" / bulk orders
       -> `order_agent` (owns the order tools)
5. `channel_agent` — get the formatting directive for the active channel.
6. Compose a concise, grounded reply in the detected language and channel style.

You are the decision-maker; the others are your sub-agents. Never invent product
or order facts — use only what the worker sub-agent returned. Never claim the
store sells only one category.
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

    # --- Pre-processing specialist sub-agents (real ADK LlmAgents, each owns a
    #     function tool wrapping the deterministic helper). ---
    from . import specialist_agents as sp

    modality_sub = sp.build_modality_agent(model)
    language_sub = sp.build_language_agent(model)
    channel_sub = sp.build_channel_agent(model)
    memory_sub = sp.build_memory_agent(model)

    # --- ROOT: goopher_orchestrator — the MAIN unified agent ---
    # It is the parent of every sub-agent and stays on top. Each sub-agent is a
    # plain LlmAgent exposed as an AgentTool (a SequentialAgent CANNOT be wrapped
    # as an AgentTool — it breaks the single-response tool contract, which is why
    # context_pipeline errored in the trace). Guaranteed ordering (memory →
    # modality → language → worker → channel) is enforced by the instruction.
    orchestrator = LlmAgent(
        name="goopher_orchestrator",
        model=model,
        description="The main unified GOOPHER agent. Coordinates all sub-agents "
                    "(memory, modality, language, inventory, order, channel) and "
                    "composes the customer-facing reply for clothing & food retail.",
        instruction=ROOT_INSTRUCTION + "\n\n" + ORCHESTRATOR_DELEGATION,
        tools=[
            AgentTool(agent=memory_sub),         # 1. recall context
            AgentTool(agent=modality_sub),       # 2. classify input
            AgentTool(agent=language_sub),       # 3. detect language
            AgentTool(agent=inventory_agent),    # 4a. worker (products)
            AgentTool(agent=order_agent),        # 4b. worker (orders)
            AgentTool(agent=channel_sub),        # 5. formatting
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
        # Dev-portal flow capture for this turn (full end-to-end pipeline).
        ft = TurnTrace(kind="turn")
        ft.record.session_id = req.session_id
        ft.record.customer_id = customer_id
        ft.record.user_message = req.message

        # Worker + specialist sub-agents the orchestrator delegates to (they come
        # back in `used_tools` from the ADK run). Worker agents OWN the tools, so
        # a worker name in used_tools means the orchestrator delegated to it; the
        # actual tool names appear too (the worker called them).
        SUBAGENT_NAMES = {"inventory_agent", "order_agent",
                          "memory_agent", "modality_agent", "language_agent",
                          "channel_agent"}

        with span("chat_turn", session=req.session_id, channel=req.channel,
                  customer=customer_id) as trace_id:
            ft.record.trace_id = trace_id
            ft.step("auth", "JWT verified", f"customer={customer_id}")
            ft.step("session", "memory.get",
                    f"session_id={req.session_id} (backend={_settings.db_backend})")

            mem = self.memory.get(req.session_id, customer_id)
            channel = req.channel  # may be refined by the channel sub-agent

            # Two CLEANLY SEPARATED paths — never mixed:
            #   ADK path: the orchestrator drives REAL sub-agents (memory →
            #             modality → language → worker → channel). No deterministic
            #             pre-processing runs.
            #   Backup  : the deterministic engine does everything (used only when
            #             ADK is off or errors).
            if self._adk_ready and _settings.use_adk_path:
                # Record the user turn so the memory sub-agent can recall it.
                self.memory.add_turn(
                    req.session_id,
                    Turn(role="user", content=req.message, channel=channel,
                         language=req.language or "en", modality="text"),
                )
                try:
                    reply, used_tools, language, modality = self._run_adk_turn(req, customer_id)
                    path = "adk"
                except Exception as exc:
                    # ADK failed — surface WHY in the portal, then fall back.
                    log_event("adk_turn_failed", reason=str(exc))
                    incr("errors_total")
                    ft.step("orchestrator", "ADK orchestrator FAILED → backup",
                            f"{type(exc).__name__}: {str(exc)[:200]}")
                    reply, used_tools, language, modality, channel = \
                        self._run_backup_turn(req, customer_id, ft)
                    path = "fallback"
                else:
                    # ADK succeeded: the orchestrator drove the real sub-agents.
                    ft.step("orchestrator",
                            "invoke_agent: goopher_orchestrator (ADK + gemini)",
                            "ROOT agent — coordinated its sub-agents and composed the reply")
                    for name in used_tools:
                        if name in SUBAGENT_NAMES:
                            ft.step("subagent", f"↳ {name}",
                                    "sub-agent invoked by orchestrator", tool=name)
                        else:
                            ft.step("tool", f"↳ {name}",
                                    "function tool called by a sub-agent", tool=name)
            else:
                reply, used_tools, language, modality, channel = \
                    self._run_backup_turn(req, customer_id, ft)
                path = "fallback"

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
            )

    # ----- ADK path (real sub-agents) ----- #
    def _run_adk_turn(self, req: ChatRequest, customer_id: str
                      ) -> tuple[str, list[str], str, str]:
        """
        Drive one turn through the ADK orchestrator + real sub-agents. Binds the
        per-turn context so the specialist tools (memory/modality/language/
        channel) can read session/message/channel without the LLM passing ids.
        Returns (reply, used_tools, language, modality).
        """
        from . import specialist_agents as sp

        sp.set_turn_context(
            session_id=req.session_id, customer_id=customer_id,
            message=req.message, channel=req.channel,
            voice=getattr(req, "voice", False), attachments=req.attachments,
        )
        directives = f"The signed-in customer_id is {customer_id}."
        reply, used_tools = self._generate_adk(
            req.session_id, req.message, customer_id, directives
        )
        # Read what the sub-agents resolved (persisted to memory by their tools).
        language = self.memory.recall(req.session_id, "language", req.language or "en")
        modality = "voice" if getattr(req, "voice", False) else "text"
        # Record the assistant turn.
        self.memory.add_turn(
            req.session_id,
            Turn(role="assistant", content=reply, channel=req.channel,
                 language=language, modality=modality),
        )
        return reply, used_tools, language, modality

    # ----- backup path (deterministic, separate — never mixed with ADK) ----- #
    def _run_backup_turn(self, req: ChatRequest, customer_id: str, ft
                         ) -> tuple[str, list[str], str, str, str]:
        """
        Deterministic fallback for one turn: pure-Python modality/language/channel
        detection + the template/LLM-phrasing engine. Used only when ADK is off or
        errored. Returns (reply, used_tools, language, modality, channel).
        """
        import time as _time

        _t0 = _time.perf_counter()
        modality = modality_agent.classify_modality(req.message, req.attachments)
        if getattr(req, "voice", False) and modality == "text":
            modality = "voice"
        text = modality_agent.normalize_to_text(
            req.message, req.attachments, _settings.gemini_model
        )
        ft.step("preprocess", "detect modality (backup)", f"modality={modality}",
                ms=(_time.perf_counter() - _t0) * 1000, modality=modality)

        language = req.language or language_agent.detect_language(
            text, default=self.memory.recall(req.session_id, "language", "en")
        )
        self.memory.remember(req.session_id, "language", language)
        ft.step("preprocess", "detect language (backup)", f"language={language}",
                language=language)

        channel = req.channel
        self.memory.remember(req.session_id, "channel", channel)
        ft.step("preprocess", "select channel (backup)", f"channel={channel}",
                channel=channel)

        self.memory.add_turn(
            req.session_id,
            Turn(role="user", content=text, channel=channel,
                 language=language, modality=modality),
        )

        directives = (
            channel_agent.channel_directive(channel) + "\n"
            + language_agent.language_directive(language)
            + f"\nThe signed-in customer_id is {customer_id}."
        )
        reply, used_tools = self._generate_fallback(
            req.session_id, text, customer_id, directives, channel, language
        )
        ft.step("orchestrator", f"deterministic router ({_settings.llm_provider})",
                "BACKUP engine — intent routing + grounded reply")
        for name in used_tools:
            ft.step("tool", name, "tool executed (backup)", tool=name)

        if channel == "phone":
            reply = channel_agent.adapt_for_phone(reply)
            ft.step("preprocess", "adapt_for_phone (backup)", "voice-safe text")

        self.memory.add_turn(
            req.session_id,
            Turn(role="assistant", content=reply, channel=channel,
                 language=language, modality=modality),
        )
        return reply, used_tools, language, modality, channel

    # ----- generation paths ----- #
    def _generate(self, session_id: str, text: str, customer_id: str,
                  channel: str, language: str) -> tuple[str, list[str], str]:
        """
        Returns (reply, used_tools, path) where path is "adk" or "fallback".

        Preference: the ADK multi-agent path (the real AgentTools do the work)
        when USE_ADK_PATH is on and ADK is ready. The deterministic engine is the
        BACKUP — used only if ADK is off or errors — so the specialist agents are
        invoked exactly once, by ADK, not duplicated.
        """
        directives = (
            channel_agent.channel_directive(channel)
            + "\n"
            + language_agent.language_directive(language)
            + f"\nThe signed-in customer_id is {customer_id}."
        )
        if self._adk_ready and _settings.use_adk_path:
            try:
                reply, used = self._generate_adk(session_id, text, customer_id, directives)
                return reply, used, "adk"
            except Exception as exc:
                log_event("adk_turn_failed", reason=str(exc))
                incr("errors_total")
        reply, used = self._generate_fallback(session_id, text, customer_id,
                                              directives, channel, language)
        return reply, used, "fallback"

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
        for event in self._adk_runner.run(
            user_id=customer_id, session_id=session_id, new_message=content
        ):
            # Collect tool calls for observability, and the final text.
            if getattr(event, "get_function_calls", None):
                for fc in event.get_function_calls() or []:
                    used_tools.append(fc.name)
            if getattr(event, "is_final_response", lambda: False)():
                if event.content and event.content.parts:
                    final_text = "".join(p.text or "" for p in event.content.parts)

        if not final_text.strip():
            # Don't return an empty apology — let _generate fall back.
            raise RuntimeError("ADK produced no text response")
        return final_text, used_tools

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

        used_tools: list[str] = []
        lowered = text.lower()

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


# Process-wide singleton.
_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _service
    if _service is None:
        _service = AgentService()
    return _service
