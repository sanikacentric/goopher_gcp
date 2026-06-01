"""
Specialist ADK sub-agents: modality, language, channel, and memory.

These are REAL ADK LlmAgents that the orchestrator can call (as AgentTools). Each
owns one or more **function tools** that wrap the proven deterministic helpers,
so the agent reasons about *when* to use the capability while the tool does the
exact, testable work.

Session binding: the tools need the current session_id / request context, which
the LLM doesn't supply. We bind it per-turn via a ContextVar set in run_turn, so
each tool call reads the right session without the model having to pass ids.

This module is only imported on the ADK path. The deterministic engine
(orchestrator._generate_fallback) is a SEPARATE backup that does NOT use these
agents — the two paths are not mixed.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

from ..memory.memory_agent import get_memory_store
from . import channel_agent, language_agent, modality_agent

# Per-turn context the specialist tools read (set by the orchestrator service).
_CTX: ContextVar[dict] = ContextVar("goopher_turn_ctx", default={})


def set_turn_context(*, session_id: str, customer_id: str, message: str,
                     channel: str, voice: bool, attachments: list) -> None:
    _CTX.set({
        "session_id": session_id, "customer_id": customer_id,
        "message": message, "channel": channel, "voice": voice,
        "attachments": attachments,
    })


def _ctx() -> dict:
    return _CTX.get()


# --------------------------------------------------------------------------- #
# Tool functions (wrap the deterministic helpers; bound to the current turn)
# --------------------------------------------------------------------------- #
def detect_modality() -> dict:
    """Classify the modality of the current request (text/voice/image/file) and
    return the normalized text. Use this first to understand the input type."""
    c = _ctx()
    modality = modality_agent.classify_modality(c.get("message", ""), c.get("attachments", []))
    if c.get("voice") and modality == "text":
        modality = "voice"
    text = modality_agent.normalize_to_text(
        c.get("message", ""), c.get("attachments", []), ""
    )
    return {"modality": modality, "normalized_text": text}


def detect_language() -> dict:
    """Detect the language of the current request (ISO code like en/es/fr) so the
    final reply can be localized. Persists it to session memory."""
    c = _ctx()
    store = get_memory_store()
    text = c.get("message", "")
    language = language_agent.detect_language(
        text, default=store.recall(c.get("session_id", ""), "language", "en")
    )
    store.remember(c.get("session_id", ""), "language", language)
    return {"language": language, "directive": language_agent.language_directive(language)}


def select_channel() -> dict:
    """Return the formatting directive for the active channel (web vs phone) so
    the reply is styled correctly (markdown for web, voice-safe for phone)."""
    c = _ctx()
    channel = c.get("channel", "web")
    get_memory_store().remember(c.get("session_id", ""), "channel", channel)
    return {"channel": channel, "directive": channel_agent.channel_directive(channel)}


def recall_session_memory() -> dict:
    """Recall recent conversation context for the current session so replies stay
    consistent across channel/language/modality switches."""
    c = _ctx()
    store = get_memory_store()
    sid = c.get("session_id", "")
    return {
        "history": store.history_text(sid, limit=8),
        "language": store.recall(sid, "language"),
        "channel": store.recall(sid, "channel"),
    }


# --------------------------------------------------------------------------- #
# ADK sub-agent builders
# --------------------------------------------------------------------------- #
def build_modality_agent(model: str):
    from google.adk.agents import LlmAgent
    return LlmAgent(
        name="modality_agent", model=model,
        description="Interprets the input modality (text/voice/image/file) and "
                    "returns the normalized request text.",
        instruction="Call detect_modality to classify the input and get the "
                    "normalized text. Report the modality and the text.",
        tools=[detect_modality],
    )


def build_language_agent(model: str):
    from google.adk.agents import LlmAgent
    return LlmAgent(
        name="language_agent", model=model,
        description="Detects the customer's language so the final reply can be "
                    "localized.",
        instruction="Call detect_language to determine the language and the "
                    "localization directive. Report the ISO code.",
        tools=[detect_language],
    )


def build_channel_agent(model: str):
    from google.adk.agents import LlmAgent
    return LlmAgent(
        name="channel_agent", model=model,
        description="Determines how to format the reply for the active channel "
                    "(web vs phone/voice).",
        instruction="Call select_channel to get the channel and its formatting "
                    "directive (markdown for web, voice-safe for phone).",
        tools=[select_channel],
    )


def build_memory_agent(model: str):
    from google.adk.agents import LlmAgent
    return LlmAgent(
        name="memory_agent", model=model,
        description="Recalls prior conversation context for the current session "
                    "to keep replies consistent across turns and switches.",
        instruction="Call recall_session_memory to fetch recent history and the "
                    "remembered language/channel for this session.",
        tools=[recall_session_memory],
    )
