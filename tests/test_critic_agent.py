"""
Tests for the RSI CriticAgent (recursive self-improvement) — isolated, hermetic.

The Gemini-as-judge call is monkeypatched (or falls back to the heuristic), so
these tests need no network/credentials. They exercise the loop: flag a failure →
heal (judge → store a confidence-gated lesson) → retrieve via keyword-RAG → the
endpoints. They also assert ISOLATION (recording a failure leaves /chat alone).
"""
import backend.app.agents.critic_agent as ca
from backend.app.agents.critic_agent import CriticAgent, LessonStore, _parse_json, _tokens
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}


def _fresh(monkeypatch):
    """Give the module a clean in-memory store + agent for the test."""
    store = LessonStore()
    monkeypatch.setattr(ca, "_STORE", store)
    monkeypatch.setattr(ca, "_AGENT", CriticAgent())
    return store


def _good_lesson(*a, **k):
    return {
        "failure_summary": "Refused a valid toy request.",
        "root_cause": "Over-cautious refusal / missed intent.",
        "lesson": "When asked about toys like dolls or balls, search the Toys department before saying no.",
        "confidence": 0.9, "applies_to_languages": ["en"], "engine": "test",
    }


# --- JSON parsing / tokens -------------------------------------------------- #
def test_parse_json_strips_code_fences():
    assert _parse_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert _parse_json("prefix {\"lesson\": \"x\"} suffix")["lesson"] == "x"
    assert _parse_json("not json") is None


def test_tokens_drop_stopwords():
    t = set(_tokens("Do you have purple unicorn dolls?"))
    assert "unicorn" in t and "dolls" in t and "you" not in t


# --- the loop --------------------------------------------------------------- #
def test_flag_then_heal_stores_lesson(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(ca, "_judge", _good_lesson)
    c = ca.get_critic()
    c.record_failure("Customer: do you have dolls?\nGOOPHER: Sorry, we don't sell toys.",
                     csat_score=2, session_id="s1")
    stats = c.run_healing_cycle()
    assert stats["evaluated"] == 1 and stats["stored"] == 1 and stats["skipped"] == 0
    assert stats["lessons"][0]["lesson"].startswith("When asked about toys")
    # failure is consumed (won't be re-judged next cycle)
    assert c.run_healing_cycle()["evaluated"] == 0


def test_heal_records_rsi_flow_to_dev_portal(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(ca, "_judge", _good_lesson)
    from backend.app.observability.flow_recorder import _recorder
    c = ca.get_critic()
    c.record_failure("Customer: do you have dolls?\nGOOPHER: no toys.", csat_score=2)
    c.run_healing_cycle()
    rec = _recorder.recent(8)[-1]
    assert rec["kind"] == "rsi"
    stages = [s["stage"] for s in rec["steps"]]
    assert stages.count("rsi") >= 3                     # DETECT, JUDGE, LESSON
    assert any("LESSON STORED" in s["name"] for s in rec["steps"])


def test_low_confidence_lesson_is_skipped(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(ca, "_judge", lambda *a, **k: {"lesson": "weak", "confidence": 0.3})
    c = ca.get_critic()
    c.record_failure("Customer: hi\nGOOPHER: hi", csat_score=3)
    stats = c.run_healing_cycle()
    assert stats["stored"] == 0 and stats["skipped"] == 1


def test_heuristic_judge_makes_the_loop_work_offline(monkeypatch):
    # No monkeypatch of _judge → uses the real _judge, which degrades to the
    # heuristic when Gemini isn't configured. The loop must still produce a lesson.
    _fresh(monkeypatch)
    c = ca.get_critic()
    c.record_failure("Customer: where is my refund?\nGOOPHER: I can't help.", csat_score=1)
    stats = c.run_healing_cycle()
    assert stats["stored"] == 1
    assert "refund" in stats["lessons"][0]["lesson"].lower()


def test_retrieve_ranks_relevant_lessons(monkeypatch):
    store = _fresh(monkeypatch)
    store.add_lesson({"lesson": "Search Toys for dolls and balls.", "confidence": 0.9,
                      "failure_summary": "toy refusal", "root_cause": "", "languages": ["en"],
                      "stored_at": "2026-01-01T00:00:00Z"})
    store.add_lesson({"lesson": "Quote the sale price for snacks.", "confidence": 0.8,
                      "failure_summary": "price", "root_cause": "", "languages": ["en"],
                      "stored_at": "2026-01-01T00:00:00Z"})
    hits = ca.get_critic().retrieve_lessons("do you have any dolls?")
    assert hits and "Toys" in hits[0]["lesson"]


# --- the loop closes: learned lessons shape the next chat answer ------------ #
def test_learned_lessons_are_injected_into_the_next_chat(monkeypatch):
    store = _fresh(monkeypatch)
    store.add_lesson({
        "lesson": "When asked for laptops or electronics we don't stock, suggest "
                  "relevant in-stock toy or gift alternatives and ask what they want.",
        "confidence": 0.9, "failure_summary": "", "root_cause": "",
        "languages": ["en"], "stored_at": "2026-01-01T00:00:00Z"})
    from backend.app.agents.orchestrator import AgentService
    from backend.app.models.schemas import ChatRequest
    resp = AgentService().run_turn(
        ChatRequest(message="do you have laptops?", session_id="rsi-chat"),
        customer_id="CUST-1001")
    # the orchestrator retrieved + applied the lesson on the LLM/fallback path
    assert "lesson_retrieve" in resp.used_tools


def test_no_lessons_leaves_chat_untouched(monkeypatch):
    _fresh(monkeypatch)  # empty store
    from backend.app.agents.orchestrator import AgentService
    from backend.app.models.schemas import ChatRequest
    resp = AgentService().run_turn(
        ChatRequest(message="do you have barbecue chips?", session_id="rsi-none"),
        customer_id="CUST-1001")
    assert "lesson_retrieve" not in resp.used_tools   # no-op when nothing matches


# --- endpoints -------------------------------------------------------------- #
def test_critic_endpoints_require_auth():
    assert client.post("/critic/flag", json={"conversation_text": "x"}).status_code == 401
    assert client.post("/critic/heal").status_code == 401
    assert client.get("/critic/lessons").status_code == 401


def test_critic_flag_heal_lessons_endpoints(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(ca, "_judge", _good_lesson)
    token = client.post("/auth/login", json=GOOD).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    r1 = client.post("/critic/flag", headers=hdr, json={
        "conversation_text": "Customer: do you have dolls?\nGOOPHER: no toys.",
        "session_id": "ep", "csat_score": 2})
    assert r1.json()["ok"] and r1.json()["flagged_id"]
    r2 = client.post("/critic/heal", headers=hdr)
    assert r2.json()["stored"] == 1
    r3 = client.get("/critic/lessons", headers=hdr)
    assert r3.json()["count"] >= 1
    assert any("toys" in L["lesson"].lower() for L in r3.json()["lessons"])
