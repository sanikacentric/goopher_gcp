"""
Flow recorder — captures the complete end-to-end pipeline of every conversation
turn so the Developer Portal can replay it: auth/session → sub-agents → tools →
memory → logs → reply.

Design: a thread-safe ring buffer of recent "flow records" plus a monotonically
increasing version counter. The Server-Sent-Events endpoint polls for records
newer than the last id it sent, which is simple and robust across FastAPI's
sync/async boundary (run_turn runs in a worker thread; the SSE generator is
async). No external deps.

Privacy note: records contain message content, session_id and customer_id. The
portal exposing them is gated by settings.dev_portal_enabled.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

_MAX_RECORDS = 200  # ring-buffer size


@dataclass
class FlowStep:
    stage: str                 # e.g. "auth", "modality", "language", "tool", "llm"
    name: str                  # human label, e.g. "language_agent: detect"
    detail: str = ""           # short human-readable detail
    ms: float = 0.0            # duration in milliseconds
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowRecord:
    id: int
    ts: float                  # epoch seconds
    kind: str                  # "login" | "turn"
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    trace_id: Optional[str] = None
    channel: Optional[str] = None
    language: Optional[str] = None
    modality: Optional[str] = None
    user_message: str = ""
    reply: str = ""
    used_tools: list[str] = field(default_factory=list)
    steps: list[FlowStep] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "kind": self.kind,
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "trace_id": self.trace_id,
            "channel": self.channel,
            "language": self.language,
            "modality": self.modality,
            "user_message": self.user_message,
            "reply": self.reply,
            "used_tools": self.used_tools,
            "memory": self.memory,
            "steps": [s.__dict__ for s in self.steps],
        }


class _Recorder:
    def __init__(self):
        self._records: list[FlowRecord] = []
        self._seq = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def add(self, record: FlowRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > _MAX_RECORDS:
                self._records = self._records[-_MAX_RECORDS:]

    def since(self, after_id: int) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._records if r.id > after_id]

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._records[-limit:]]


_recorder = _Recorder()


def get_recorder() -> _Recorder:
    return _recorder


class TurnTrace:
    """
    Helper passed through a single turn to accumulate steps, then committed to
    the recorder. Use `.step(...)` to log a stage with timing.
    """

    def __init__(self, kind: str = "turn"):
        self.record = FlowRecord(id=_recorder.next_id(), ts=time.time(), kind=kind)

    def step(self, stage: str, name: str, detail: str = "", ms: float = 0.0,
             **data: Any) -> None:
        self.record.steps.append(
            FlowStep(stage=stage, name=name, detail=detail, ms=round(ms, 2), data=data)
        )

    def commit(self) -> None:
        _recorder.add(self.record)


def record_login(customer_id: str, email: str, ok: bool) -> None:
    """Record an auth attempt as its own flow entry."""
    rec = FlowRecord(
        id=_recorder.next_id(), ts=time.time(), kind="login",
        customer_id=customer_id if ok else None,
        user_message=f"login: {email}",
        reply="authenticated" if ok else "REJECTED",
    )
    rec.steps.append(
        FlowStep(stage="auth", name="authenticate",
                 detail=("allowlisted email + master password OK" if ok
                         else "rejected (allowlist/password)"))
    )
    _recorder.add(rec)
