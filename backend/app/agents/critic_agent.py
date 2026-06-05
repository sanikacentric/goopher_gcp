"""
CriticAgent — Recursive Self-Improvement (RSI), Layer-3 self-heal (NEW, ISOLATED).

GOOPHER already self-heals its INFRASTRUCTURE (the Guardian: circuit breaker /
failover). The CriticAgent closes the *behavioural* loop — it learns from its own
failures, with **no retraining and no redeployment**:

    low-satisfaction conversation
      → Gemini-as-judge  (gemini-2.5-flash on Vertex): score + root cause + LESSON
      → store the lesson (confidence-gated) in the lessons knowledge base
      → lesson_retrieve (RAG) surfaces the top-k lessons for a new, similar query

This module is **fully self-contained** and does NOT modify the chat orchestrator
or any existing flow — it has its own store and its own `POST /critic/*`
endpoints. The production-grade version of the storage/retrieval would use
**Vertex AI Embeddings + Vertex AI Vector Search (+ AlloyDB metadata)** and run as
a **Cloud Run Job every 15 min via Cloud Scheduler**; here we keep it dependency-
light (Firestore in cloud / in-memory locally, keyword-RAG) so it runs and demos
anywhere. The judge call mirrors the Vision/Advisor pattern: `google.genai` on
Vertex, `thinking_budget=0`, JSON output — never the legacy SDK / 2.0-flash.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from ..config import get_settings
from ..observability.telemetry import incr, log_event

# Only lessons the judge is at least this confident about are stored.
MIN_CONFIDENCE_TO_STORE = float(os.getenv("MIN_LESSON_CONFIDENCE", "0.70"))

JUDGE_PROMPT = """You are a quality evaluator for a retail AI shopping assistant (GOOPHER),
which sells women's casual Clothing, Food/Snacks, and Toys.

Below is a customer conversation where the agent gave an unsatisfactory (often
vague or flatly-refusing) response. Return a JSON object with EXACTLY these fields:
{
  "failure_summary": "<one sentence: what went wrong>",
  "root_cause": "<e.g. flat refusal with no alternative, missed intent, ambiguous query, missing context>",
  "lesson": "<a CONCRETE behavioural instruction the agent can FOLLOW on the next similar turn>",
  "confidence": <float 0.0-1.0>,
  "applies_to_languages": ["en", ...]
}

Rules for the "lesson" (this is the most important field):
- Start with a verb; describe what to SAY or DO differently IN THE CONVERSATION.
- It must be reusable for similar future queries — not a one-off.
- Do NOT propose infra/data/catalog fixes (e.g. "make the catalog comprehensive") —
  those are not actionable mid-conversation.
- If the customer asked for something we don't sell, the lesson should be to briefly
  acknowledge we don't carry it, THEN proactively suggest the closest relevant
  in-stock items from Clothing/Food/Toys and ask one clarifying question.

GOOD lesson: "When a customer asks for an item we don't sell (e.g. electronics like
laptops or phones), acknowledge we don't carry it, then proactively suggest relevant
in-stock alternatives — e.g. tech-style toys or a gift idea — and ask what they're
shopping for, so they always leave with a next step."
BAD lesson: "Ensure the product catalog is comprehensive." (not actionable in-chat)

Conversation:
%(conversation)s

Customer satisfaction score: %(csat)s/5
Agent: %(agent)s

Return ONLY valid JSON. No markdown, no preamble."""


# --------------------------------------------------------------------------- #
# Lessons knowledge base (Firestore in cloud · in-memory locally)
# --------------------------------------------------------------------------- #
class LessonStore:
    """Stores failures + learned lessons and retrieves top-k lessons (keyword RAG).

    Cloud: Firestore collections `rsi_failures` / `rsi_lessons` (reusing the
    repository's client). Local/test: in-memory lists. Production upgrade path:
    Vertex AI Embeddings + Vector Search for semantic retrieval (see module doc)."""

    def __init__(self):
        self._fs = None
        self._failures: list[dict] = []
        self._lessons: list[dict] = []
        self._seq = 0
        try:
            from ..db.database import get_repository
            repo = get_repository()
            if hasattr(repo, "db"):           # FirestoreRepository exposes `.db`
                self._fs = repo.db
        except Exception as exc:  # noqa: BLE001 - degrade to in-memory
            log_event("rsi_store_local", reason=str(exc))

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{int(time.time())}-{self._seq}"

    # -- failures -- #
    def add_failure(self, rec: dict) -> dict:
        rec = {"id": self._next_id("fail"), "status": "pending", **rec}
        if self._fs is not None:
            self._fs.collection("rsi_failures").document(rec["id"]).set(rec)
        else:
            self._failures.append(rec)
        return rec

    def pending_failures(self) -> list[dict]:
        if self._fs is not None:
            return [d.to_dict() for d in
                    self._fs.collection("rsi_failures").where("status", "==", "pending").stream()]
        return [f for f in self._failures if f.get("status") == "pending"]

    def mark_processed(self, fail_id: str) -> None:
        if self._fs is not None:
            self._fs.collection("rsi_failures").document(fail_id).set({"status": "processed"}, merge=True)
        else:
            for f in self._failures:
                if f["id"] == fail_id:
                    f["status"] = "processed"

    # -- lessons -- #
    def add_lesson(self, rec: dict) -> dict:
        rec = {"id": self._next_id("lesson"), **rec}
        if self._fs is not None:
            self._fs.collection("rsi_lessons").document(rec["id"]).set(rec)
        else:
            self._lessons.append(rec)
        return rec

    def all_lessons(self) -> list[dict]:
        if self._fs is not None:
            rows = [d.to_dict() for d in self._fs.collection("rsi_lessons").stream()]
        else:
            rows = list(self._lessons)
        rows.sort(key=lambda r: r.get("stored_at", ""), reverse=True)
        return rows

    def retrieve(self, query: str, k: int = 3, language: Optional[str] = None) -> list[dict]:
        """Top-k lessons relevant to `query` (keyword overlap + confidence/recency)."""
        q = set(_tokens(query))
        if not q:
            return []
        scored = []
        for L in self.all_lessons():
            if language and L.get("languages") and language not in L["languages"]:
                continue
            hay = _tokens(" ".join([L.get("lesson", ""), L.get("failure_summary", ""),
                                    L.get("root_cause", "")]))
            overlap = len(q & set(hay))
            if overlap:
                score = overlap + 0.5 * float(L.get("confidence", 0))
                scored.append((score, L))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [L for _, L in scored[:k]]


_STOP = {"the", "a", "an", "is", "are", "do", "does", "you", "i", "to", "of", "for",
         "in", "on", "and", "or", "it", "this", "that", "my", "me", "we", "have",
         "can", "with", "what", "where", "how", "please", "want"}


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOP]


_STORE: Optional[LessonStore] = None


def get_store() -> LessonStore:
    global _STORE
    if _STORE is None:
        _STORE = LessonStore()
    return _STORE


# --------------------------------------------------------------------------- #
# Gemini-as-judge
# --------------------------------------------------------------------------- #
def _gemini_client(settings):
    from google import genai
    if settings.use_vertexai:
        return genai.Client(vertexai=True, project=settings.google_cloud_project,
                            location=settings.vertex_location)
    if settings.google_api_key:
        return genai.Client(api_key=settings.google_api_key)
    return None


def _judge(conversation: str, csat: int, agent: str) -> dict:
    """Gemini-as-judge → {failure_summary, root_cause, lesson, confidence,
    applies_to_languages, engine}. Degrades to a heuristic lesson if Gemini isn't
    available, so the loop always demos (offline/local included)."""
    settings = get_settings()
    prompt = JUDGE_PROMPT % {"conversation": conversation[:4000], "csat": csat, "agent": agent}
    try:
        client = _gemini_client(settings)
        if client is not None:
            from google.genai import types
            cfg = {"max_output_tokens": 1024, "temperature": 0.1,
                   "response_mime_type": "application/json"}
            try:
                cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
            resp = client.models.generate_content(
                model=settings.gemini_model, contents=[prompt],
                config=types.GenerateContentConfig(**cfg))
            text = _extract_text(resp)
            data = _parse_json(text)
            if data and data.get("lesson"):
                data["engine"] = "gemini-2.5-flash-judge"
                return data
            log_event("rsi_judge_empty")
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        log_event("rsi_judge_failed", reason=str(exc))
    return _heuristic_lesson(conversation, csat, agent)


def _extract_text(resp) -> str:
    cands = getattr(resp, "candidates", None) or []
    if not cands:
        return ""
    parts = (getattr(getattr(cands[0], "content", None), "parts", None) or [])
    return "".join(getattr(p, "text", "") or "" for p in parts).strip()


def _parse_json(text: str) -> Optional[dict]:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group(0) if m else t)
    except Exception:  # noqa: BLE001
        return None


def _heuristic_lesson(conversation: str, csat: int, agent: str) -> dict:
    """Deterministic fallback so RSI demos without an LLM. Pulls the customer's
    last question and writes a generic corrective lesson."""
    asks = re.findall(r"(?:customer|user)\s*:\s*(.+)", conversation, re.IGNORECASE)
    topic = (asks[-1] if asks else conversation[:80]).strip()[:120]
    return {
        "failure_summary": f"The customer was unsatisfied with the reply to: “{topic}”.",
        "root_cause": "Likely a missed intent or an unhelpful/over-cautious response.",
        "lesson": (f"When a customer asks something like “{topic}”, answer directly "
                   "and, if unsure, offer the closest in-stock option or ask one "
                   "clarifying question — never leave them without a next step."),
        "confidence": 0.75,
        "applies_to_languages": ["en"],
        "engine": "heuristic",
    }


# --------------------------------------------------------------------------- #
# The agent
# --------------------------------------------------------------------------- #
class CriticAgent:
    """Evaluates flagged failures and writes lessons to the knowledge base."""

    def record_failure(self, conversation_text: str, csat_score: int = 2,
                       agent_name: str = "goopher", session_id: str = "") -> dict:
        incr("rsi_failures_flagged")
        rec = get_store().add_failure({
            "session_id": session_id, "conversation_text": conversation_text,
            "csat_score": int(csat_score), "agent_name": agent_name,
            "ts": _now(),
        })
        log_event("rsi_failure_flagged", session=session_id, csat=csat_score)
        return rec

    def run_healing_cycle(self) -> dict:
        """Judge every pending failure; store high-confidence lessons. Returns
        stats + the lessons learned this cycle (for the live demo). Also records
        the cycle to the /dev portal (kind="rsi": DETECT → JUDGE → LESSON)."""
        store = get_store()
        pending = store.pending_failures()
        stats = {"evaluated": 0, "stored": 0, "skipped": 0, "lessons": []}

        ft = None
        try:
            from ..observability.flow_recorder import TurnTrace
            ft = TurnTrace(kind="rsi")
            ft.record.user_message = "Recursive self-improvement cycle (CriticAgent)"
        except Exception:  # noqa: BLE001 - portal recording must never break the cycle
            ft = None

        for f in pending:
            stats["evaluated"] += 1
            convo = f.get("conversation_text", "")
            topic = _topic(convo)
            if ft:
                ft.step("rsi", "🔎 DETECT — flagged conversation",
                        f"csat {f.get('csat_score', 2)}/5 · “{topic}”")
            ev = _judge(convo, f.get("csat_score", 2), f.get("agent_name", "goopher"))
            store.mark_processed(f["id"])
            conf = float(ev.get("confidence", 0) or 0)
            lesson = ev.get("lesson", "")
            if ft:
                ft.step("rsi", f"🧠 JUDGE — Gemini-as-judge ({ev.get('engine', '?')})",
                        f"root cause: {ev.get('root_cause', '')[:140]}")
            if conf < MIN_CONFIDENCE_TO_STORE or not lesson:
                stats["skipped"] += 1
                if ft:
                    ft.step("rsi", f"⏭ SKIPPED — confidence {conf:.0%} < {MIN_CONFIDENCE_TO_STORE:.0%}",
                            "lesson not stored")
                log_event("rsi_lesson_below_threshold", confidence=conf)
                continue
            rec = store.add_lesson({
                "failure_summary": ev.get("failure_summary", ""),
                "root_cause": ev.get("root_cause", ""),
                "lesson": lesson,
                "agent_name": f.get("agent_name", "goopher"),
                "confidence": conf,
                "languages": ev.get("applies_to_languages", ["en"]),
                "csat_score": f.get("csat_score", 2),
                "engine": ev.get("engine", "?"),
                "stored_at": _now(),
            })
            stats["stored"] += 1
            stats["lessons"].append(rec)
            if ft:
                ft.step("rsi", f"💡 LESSON STORED — confidence {conf:.0%}", lesson[:200])
            log_event("rsi_lesson_stored", confidence=round(conf, 3), lesson=lesson[:80])

        if ft:
            try:
                ft.record.reply = (f"Evaluated {stats['evaluated']} · stored "
                                   f"{stats['stored']} lesson(s) · skipped {stats['skipped']}")
                ft.commit()
            except Exception:  # noqa: BLE001
                pass
        log_event("rsi_healing_cycle", **{k: v for k, v in stats.items() if k != "lessons"})
        return stats

    def retrieve_lessons(self, query: str, k: int = 3,
                         language: Optional[str] = None) -> list[dict]:
        return get_store().retrieve(query, k=k, language=language)

    def answer_with_lessons(self, query: str, language: str = "en") -> dict:
        """SELF-CONTAINED demo of `lesson_retrieve`: retrieve top-k lessons for the
        query and let Gemini answer WITH them as guidance (RAG). Proves the loop's
        payoff without touching the production /chat path."""
        lessons = self.retrieve_lessons(query, k=3, language=language)
        guidance = "\n".join(f"- {L['lesson']}" for L in lessons) or "(none yet)"
        settings = get_settings()
        prompt = (
            "You are GOOPHER, a retail shopping assistant. Apply these LEARNED "
            "LESSONS from past mistakes before answering:\n" + guidance +
            f"\n\nCustomer: {query}\nGOOPHER:")
        answer, engine = "", "none"
        try:
            client = _gemini_client(settings)
            if client is not None:
                from google.genai import types
                cfg = {"max_output_tokens": 512, "temperature": 0.3}
                try:
                    cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
                resp = client.models.generate_content(
                    model=settings.gemini_model, contents=[prompt],
                    config=types.GenerateContentConfig(**cfg))
                answer = _extract_text(resp)
                engine = "gemini-2.5-flash"
        except Exception as exc:  # noqa: BLE001
            log_event("rsi_answer_failed", reason=str(exc))
        if not answer:
            answer = ("Here's my best help based on what I've learned: "
                      + (lessons[0]["lesson"] if lessons else
                         "I'll find the closest in-stock option for you."))
            engine = "fallback"
        return {"answer": answer, "lessons_used": lessons, "engine": engine}


def _topic(conversation: str) -> str:
    """The customer's last question, for a compact /dev label."""
    asks = re.findall(r"(?:customer|user)\s*:\s*(.+)", conversation, re.IGNORECASE)
    return (asks[-1] if asks else conversation[:80]).strip()[:90]


def _now() -> str:
    # time.time() is allowed; avoid datetime.now() to keep imports light.
    t = time.gmtime()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


_AGENT: Optional[CriticAgent] = None


def get_critic() -> CriticAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = CriticAgent()
    return _AGENT


# --------------------------------------------------------------------------- #
# Cloud Run Job entrypoint (production: Cloud Scheduler triggers this every 15m)
# --------------------------------------------------------------------------- #
def main() -> None:  # pragma: no cover - operational entrypoint
    stats = get_critic().run_healing_cycle()
    print(f"RSI healing cycle complete: "
          f"evaluated={stats['evaluated']} stored={stats['stored']} skipped={stats['skipped']}")


if __name__ == "__main__":  # pragma: no cover
    main()
