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
    kind: str                  # "login" | "turn" | "fulfillment"
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
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
            "order_id": self.order_id,
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
    """
    Thread-safe store of flow records, DEDUPED BY RECORD ID.

    A record (e.g. a fulfillment pipeline) is committed repeatedly as it
    advances — once per stage. We must NOT store a new copy each time (that's
    what made the dev portal show the same pipeline 9×). Instead we upsert by
    id and bump a monotonic VERSION counter, so:
      * `recent()` returns each record exactly once (latest state), and
      * `since(version)` re-returns a record whenever it's updated, letting the
        live stream push refreshed copies that the portal merges into one card.
    """

    def __init__(self):
        self._records: dict[int, FlowRecord] = {}   # id -> record (deduped)
        self._ver: dict[int, int] = {}              # id -> version at last update
        self._seq = 0      # record-id sequence
        self._vseq = 0     # global version sequence
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def add(self, record: FlowRecord) -> None:
        """Insert or update a record (deduped by id), bumping its version so the
        live stream re-sends the refreshed copy."""
        with self._lock:
            self._vseq += 1
            self._records[record.id] = record
            self._ver[record.id] = self._vseq
            if len(self._records) > _MAX_RECORDS:
                for rid in sorted(self._records)[:len(self._records) - _MAX_RECORDS]:
                    self._records.pop(rid, None)
                    self._ver.pop(rid, None)

    def current_version(self) -> int:
        with self._lock:
            return self._vseq

    def since(self, after_version: int) -> list[dict]:
        """Records changed since `after_version`, oldest change first."""
        with self._lock:
            changed = [(self._ver[rid], r) for rid, r in self._records.items()
                       if self._ver[rid] > after_version]
        changed.sort(key=lambda vr: vr[0])
        return [r.to_dict() for _, r in changed]

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            ids = sorted(self._records)[-limit:]
            return [self._records[rid].to_dict() for rid in ids]


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


def new_pipeline_record(order_id: str, customer_id: str) -> FlowRecord:
    """
    Start a dedicated ORDER-MANAGEMENT pipeline record (its own card in the dev
    portal, kind='fulfillment'). Append stages with add_pipeline_stage and commit
    with commit_record once each stage completes — so stakeholders see it advance
    live (inventory check in progress -> complete -> ... -> delivered).
    """
    return FlowRecord(
        id=_recorder.next_id(), ts=time.time(), kind="fulfillment",
        order_id=order_id, customer_id=customer_id,
        user_message=f"Order management pipeline for {order_id}",
    )


def commit_record(rec: FlowRecord) -> None:
    """Publish/refresh a record so the live portal reflects its current steps."""
    _recorder.add(rec)
