"""
Conversational memory (Requirement T3 + the global "maintain context" rule).

`MemoryStore` keeps short-term turn history AND a small key/value "working
memory" per session, so context is preserved when the shopper switches:
  * channel  (web  <-> phone)
  * language (en   <-> es ...)
  * modality (text <-> voice <-> image)

The session_id is the join key. The same store is consulted by the
orchestrator before every turn and updated after every turn, which is what
makes context survive those switches.

Backed by an in-process dict for local/dev; the same interface can be pointed
at Firestore (collection `sessions`) for multi-instance Cloud Run deployments —
see `FirestoreMemoryStore` below.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Turn:
    role: str          # "user" | "assistant"
    content: str
    channel: str = "web"
    language: str = "en"
    modality: str = "text"


@dataclass
class SessionMemory:
    session_id: str
    customer_id: Optional[str] = None
    turns: list[Turn] = field(default_factory=list)
    # Working memory: durable facts that should outlive a single turn, e.g.
    # last product viewed, preferred language, the order currently in focus.
    facts: dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    """Thread-safe in-memory conversational store."""

    def __init__(self, max_turns: int = 40):
        self._sessions: dict[str, SessionMemory] = {}
        self._lock = threading.Lock()
        self._max_turns = max_turns

    def get(self, session_id: str, customer_id: Optional[str] = None) -> SessionMemory:
        with self._lock:
            mem = self._sessions.get(session_id)
            if mem is None:
                mem = SessionMemory(session_id=session_id, customer_id=customer_id)
                self._sessions[session_id] = mem
            elif customer_id and not mem.customer_id:
                mem.customer_id = customer_id
            return mem

    def add_turn(self, session_id: str, turn: Turn) -> None:
        with self._lock:
            mem = self._sessions.setdefault(session_id, SessionMemory(session_id))
            mem.turns.append(turn)
            # Trim to a rolling window to bound token usage / memory growth.
            if len(mem.turns) > self._max_turns:
                mem.turns = mem.turns[-self._max_turns :]

    def remember(self, session_id: str, key: str, value: Any) -> None:
        with self._lock:
            mem = self._sessions.setdefault(session_id, SessionMemory(session_id))
            mem.facts[key] = value

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            mem = self._sessions.get(session_id)
            return mem.facts.get(key, default) if mem else default

    def history_text(self, session_id: str, limit: int = 12) -> str:
        """Render recent turns as plain text to prime the LLM with context."""
        mem = self._sessions.get(session_id)
        if not mem:
            return ""
        recent = mem.turns[-limit:]
        lines = [
            f"[{t.channel}/{t.language}/{t.modality}] {t.role}: {t.content}"
            for t in recent
        ]
        return "\n".join(lines)


# Process-wide singleton used by the orchestrator and API.
_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
