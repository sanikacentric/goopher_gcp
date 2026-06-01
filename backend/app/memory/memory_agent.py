"""
Conversational memory (Requirement T3 + the global "maintain context" rule).

A memory store keeps short-term turn history AND a small key/value "working
memory" per session, so context is preserved when the shopper switches:
  * channel  (web  <-> phone)
  * language (en   <-> es ...)
  * modality (text <-> voice <-> image)

The session_id is the join key. The same store is consulted by the orchestrator
before every turn and updated after every turn, which is what makes context
survive those switches.

Two interchangeable backends behind one interface:
  * InMemoryStore   — a process-local dict. Fine for local dev / a single
                      instance, but conversation context is LOST when Cloud Run
                      scales to multiple instances or scales to zero.
  * FirestoreStore  — persists each session as a document in the `sessions`
                      collection (Firestore free tier). Survives autoscaling,
                      cold starts, and restarts, and is shared across instances,
                      so the SAME session_id resolves to the SAME conversation
                      everywhere. This is what production uses.

Backend is chosen by `settings.db_backend` ("sqlite" -> in-memory,
"firestore" -> Firestore), matching the data layer.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ..config import get_settings
from ..observability.telemetry import log_event

_settings = get_settings()


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


def _history_text(mem: SessionMemory, limit: int) -> str:
    """Render recent turns as plain text to prime the LLM with context."""
    recent = mem.turns[-limit:]
    return "\n".join(
        f"[{t.channel}/{t.language}/{t.modality}] {t.role}: {t.content}"
        for t in recent
    )


# --------------------------------------------------------------------------- #
# In-memory backend (local / single instance)
# --------------------------------------------------------------------------- #
class InMemoryStore:
    """Thread-safe process-local conversational store."""

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
        mem = self._sessions.get(session_id)
        return _history_text(mem, limit) if mem else ""


# --------------------------------------------------------------------------- #
# Firestore backend (production: survives autoscaling, shared across instances)
# --------------------------------------------------------------------------- #
class FirestoreStore:
    """
    Conversational store backed by Firestore (collection `sessions`).

    Each session_id is one document holding {customer_id, turns[], facts{}}.
    Because Firestore is a shared managed database, the SAME session_id always
    resolves to the SAME conversation regardless of which Cloud Run instance
    serves the request — which is exactly what fixes the multi-instance context
    loss. Turns are trimmed to a rolling window to bound document size/cost.
    """

    def __init__(self, project: str, database: str = "(default)",
                 max_turns: int = 40, collection: str = "sessions"):
        from google.cloud import firestore  # lazy import (cloud-only dep)

        self._db = firestore.Client(project=project, database=database)
        self._col = self._db.collection(collection)
        self._max_turns = max_turns
        log_event("memory_backend_init", backend="firestore", collection=collection)

    def _doc(self, session_id: str):
        return self._col.document(session_id)

    def _load(self, session_id: str) -> Optional[SessionMemory]:
        snap = self._doc(session_id).get()
        if not snap.exists:
            return None
        d = snap.to_dict() or {}
        turns = [Turn(**t) for t in d.get("turns", [])]
        return SessionMemory(
            session_id=session_id,
            customer_id=d.get("customer_id"),
            turns=turns,
            facts=d.get("facts", {}),
        )

    def get(self, session_id: str, customer_id: Optional[str] = None) -> SessionMemory:
        mem = self._load(session_id)
        if mem is None:
            mem = SessionMemory(session_id=session_id, customer_id=customer_id)
            # Persist a stub so the session_id is durably registered immediately.
            self._doc(session_id).set(
                {"session_id": session_id, "customer_id": customer_id,
                 "turns": [], "facts": {}}
            )
        elif customer_id and not mem.customer_id:
            mem.customer_id = customer_id
            self._doc(session_id).set({"customer_id": customer_id}, merge=True)
        return mem

    def add_turn(self, session_id: str, turn: Turn) -> None:
        mem = self._load(session_id) or SessionMemory(session_id=session_id)
        mem.turns.append(turn)
        if len(mem.turns) > self._max_turns:
            mem.turns = mem.turns[-self._max_turns :]
        self._doc(session_id).set(
            {"session_id": session_id,
             "customer_id": mem.customer_id,
             "turns": [asdict(t) for t in mem.turns]},
            merge=True,
        )

    def remember(self, session_id: str, key: str, value: Any) -> None:
        # Dotted field path updates only the one fact, avoiding a full read/write.
        self._doc(session_id).set(
            {"session_id": session_id, "facts": {key: value}}, merge=True
        )

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        mem = self._load(session_id)
        return mem.facts.get(key, default) if mem else default

    def history_text(self, session_id: str, limit: int = 12) -> str:
        mem = self._load(session_id)
        return _history_text(mem, limit) if mem else ""


# --------------------------------------------------------------------------- #
# Factory (process-wide singleton)
# --------------------------------------------------------------------------- #
_store: Optional[object] = None


def get_memory_store():
    """
    Return the configured memory store. Firestore when db_backend=="firestore"
    (production: shared, survives scaling); otherwise the in-memory store. Falls
    back to in-memory if the Firestore client can't be created, so the service
    never hard-fails on a memory-backend issue.
    """
    global _store
    if _store is not None:
        return _store

    if _settings.db_backend == "firestore":
        try:
            _store = FirestoreStore(
                _settings.google_cloud_project, _settings.firestore_database
            )
            return _store
        except Exception as exc:  # pragma: no cover - cloud-only path
            log_event("memory_backend_fallback", reason=str(exc))

    _store = InMemoryStore()
    log_event("memory_backend_init", backend="in_memory")
    return _store
