"""
GOOPHER Orchestrator (Requirement T2: ADK ORCHESTRATOR FOR AGENTS).

This is the unified conversational agent. It:
  * Composes the inventory & order AGENT SKILLS (T4) as tools.
  * Coordinates three SUBAGENTS — channel (2A-4), language (2A-5), modality
    (2A-6) — to satisfy multi-channel / multi-lingual / multi-modal needs.
  * Uses the MEMORY agent (T3) to maintain context across channel/language/
    modality switches (global "maintain context" requirement).
  * Uses Gemini (T6) as the LLM and MCP tools (T5) as the backend integration.
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

from ..config import get_settings
from ..memory.memory_agent import Turn, get_memory_store
from ..models.schemas import ChatRequest, ChatResponse
from ..observability.telemetry import incr, log_event, span
from . import channel_agent, language_agent, modality_agent
from .skills import inventory_skill, order_skill

_settings = get_settings()


ROOT_INSTRUCTION = """
You are GOOPHER, a friendly, efficient shopping assistant for an online store
with TWO departments: women's casual Clothing and Food/Snacks. You help
customers discover products in EITHER department, check live inventory, and
manage their orders (single or in bulk).

Rules:
- The store sells BOTH clothing (dresses) AND food/snacks (chips, cookies, soda,
  peanuts, crackers, snack bars). NEVER say you only sell dresses/clothing.
- Use the inventory tools for any availability/price/product question, in either
  department. TRUST the tool results: if a product appears in the tool results,
  the store sells it — present it. Never refuse an item the tools returned.
- Use the order tools for any order-status question. The signed-in customer's
  id is given to you; never ask the user for it.
- Be concise and proactive. Surface low-stock warnings and the current sale price.
- Stay on the topic of the store's clothing & food products and order help.
- Honor the CHANNEL and LANGUAGE directives provided for this turn.
""".strip()


# --------------------------------------------------------------------------- #
# ADK agent tree
# --------------------------------------------------------------------------- #
def build_root_agent():
    """
    Construct the ADK orchestrator: a root LlmAgent that owns the skill tools
    and delegates to the channel/language/modality subagents.

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

    tools = inventory_skill.get_tools() + order_skill.get_tools()

    root = LlmAgent(
        name="goopher_orchestrator",
        model=_settings.gemini_model,
        description="Unified conversational retail agent for clothing & food.",
        instruction=ROOT_INSTRUCTION
        + "\n\n"
        + inventory_skill.INSTRUCTION
        + "\n\n"
        + order_skill.INSTRUCTION,
        tools=tools,
        sub_agents=[
            channel_agent.build_adk_agent(_settings.gemini_model),
            language_agent.build_adk_agent(_settings.gemini_model),
            modality_agent_stub(_settings.gemini_model),
        ],
    )
    return root


def modality_agent_stub(model: str):
    """ADK sub-agent registration for modality handling (logic lives in
    modality_agent.py; this exposes it to the LLM as a delegatable agent)."""
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name="modality_agent",
        model=model,
        description="Normalizes voice/image/file inputs into text attributes.",
        instruction=(
            "You interpret non-text inputs (image descriptions, extracted file "
            "data) and restate them as concrete shopping or order intents."
        ),
    )


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
        incr("chat_requests_total")
        with span("chat_turn", session=req.session_id, channel=req.channel,
                  customer=customer_id) as trace_id:
            mem = self.memory.get(req.session_id, customer_id)

            # 1) MODALITY subagent: fold any attachments into text.
            modality = modality_agent.classify_modality(req.message, req.attachments)
            text = modality_agent.normalize_to_text(
                req.message, req.attachments, _settings.gemini_model
            )

            # 2) LANGUAGE subagent: detect or honor preferred language.
            language = req.language or language_agent.detect_language(
                text, default=self.memory.recall(req.session_id, "language", "en")
            )
            self.memory.remember(req.session_id, "language", language)

            # 3) CHANNEL subagent: build a style directive.
            channel = req.channel
            self.memory.remember(req.session_id, "channel", channel)

            # Record the user turn BEFORE answering (memory / context).
            self.memory.add_turn(
                req.session_id,
                Turn(role="user", content=text, channel=channel,
                     language=language, modality=modality),
            )

            # 4) Generate the reply (ADK path or fallback), with tools.
            reply, used_tools = self._generate(req.session_id, text, customer_id,
                                               channel, language)

            # 5) CHANNEL post-processing for phone (voice-safe text).
            if channel == "phone":
                reply = channel_agent.adapt_for_phone(reply)

            # Record the assistant turn.
            self.memory.add_turn(
                req.session_id,
                Turn(role="assistant", content=reply, channel=channel,
                     language=language, modality=modality),
            )

            log_event("chat_reply", session=req.session_id, language=language,
                      channel=channel, modality=modality, used_tools=used_tools,
                      trace_id=trace_id)
            return ChatResponse(
                reply=reply, session_id=req.session_id, language=language,
                channel=channel, used_tools=used_tools, trace_id=trace_id,
            )

    # ----- generation paths ----- #
    def _generate(self, session_id: str, text: str, customer_id: str,
                  channel: str, language: str) -> tuple[str, list[str]]:
        directives = (
            channel_agent.channel_directive(channel)
            + "\n"
            + language_agent.language_directive(language)
            + f"\nThe signed-in customer_id is {customer_id}."
        )
        # Choose the generation path. By default we use the grounded
        # "tools + Gemini phrasing" path (reliable: it always routes to the right
        # tool and never refuses/hallucinates, while still using Gemini for the
        # reply). The raw ADK multi-agent path is opt-in via USE_ADK_PATH=true.
        if self._adk_ready and _settings.use_adk_path:
            try:
                return self._generate_adk(session_id, text, customer_id, directives)
            except Exception as exc:
                log_event("adk_turn_failed", reason=str(exc))
                incr("errors_total")
        return self._generate_fallback(session_id, text, customer_id, directives,
                                      channel, language)

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
        from ..mcp.inventory_tool import check_stock, search_inventory
        from ..mcp.order_tool import bulk_order_status, get_order_status, list_customer_orders

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
