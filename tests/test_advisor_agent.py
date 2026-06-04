"""
Tests for the NEW Shopping-Advisor subagent (explicit ReAct / PlanReActPlanner)
and POST /advise.

The agent is exercised WITHOUT a live Gemini/ADK call: we test the ReAct output
parser, the read-only isolation guarantee, the graceful-degradation path, and
the endpoint wiring — all hermetic (no network, camera, or API key).
"""
import backend.app.agents.advisor_agent as adv
from backend.app.agents.advisor_agent import _split_react, handle_advise
from backend.app.agents.harness import AgentRunResult
from backend.app.agents.skills import checkout_skill, inventory_skill, order_skill
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}


# --- ReAct output parsing ------------------------------------------------- #
def test_split_react_extracts_plan_and_final():
    raw = (
        "/*PLANNING*/\n1. look up last order\n2. search snacks under $4\n"
        "/*ACTION*/ search_inventory(snacks)\n"
        "/*REASONING*/ Cheez-It at $3.49 pairs with cookies and is under budget.\n"
        "/*FINAL_ANSWER*/ I'd recommend Cheez-It Original at $3.49."
    )
    final, plan = _split_react(raw)
    assert final == "I'd recommend Cheez-It Original at $3.49."
    assert "PLAN" in plan and "REASONING" in plan          # tags prettified
    assert "/*FINAL_ANSWER*/" not in plan                  # final stripped out
    assert "/*PLANNING*/" not in plan                      # raw tags removed


def test_split_react_without_tags_returns_text_as_reply():
    final, plan = _split_react("Just a plain recommendation, no tags.")
    assert final == "Just a plain recommendation, no tags."
    assert plan == ""


def test_split_react_plan_without_final_does_not_leak_tags():
    # The "plan but no final answer" stall: raw tags must NOT become the reply;
    # the plan goes to the panel and the reply is left empty for the safety net.
    raw = "/*PLANNING*/\n1. list orders\n/*ACTION*/ search_inventory(snacks)"
    final, plan = _split_react(raw)
    assert final == ""
    assert "PLAN" in plan and "ACTION" in plan
    assert "/*PLANNING*/" not in plan and "/*ACTION*/" not in plan


# --- Read-only isolation guarantee ---------------------------------------- #
def test_advisor_tools_are_read_only_no_checkout():
    """The advisor must NEVER be able to place an order: its tool set must be
    disjoint from the checkout skill's tools."""
    advisor_tools = set(inventory_skill.get_tools()) | set(order_skill.get_tools())
    checkout_tools = set(checkout_skill.get_tools())
    assert advisor_tools.isdisjoint(checkout_tools)
    names = {t.__name__ for t in advisor_tools}
    assert not any(("place" in n or "checkout" in n or "pay" in n) for n in names)


def test_handle_advise_never_returns_a_checkout():
    """Even on the unavailable path, the advisor result carries no checkout."""
    out = handle_advise("a snack under $4", "CUST-1001", "adv-x")
    assert "checkout" not in out


# --- Graceful degradation when the ADK/ReAct path isn't available --------- #
def test_handle_advise_graceful_when_harness_unavailable(monkeypatch):
    # The common harness couldn't build the agent (no ADK) → unavailable message.
    monkeypatch.setattr(adv._HARNESS, "run",
                        lambda **k: AgentRunResult(ok=False, error="no adk"))
    monkeypatch.setattr(adv._HARNESS, "ready", lambda: False)
    out = handle_advise("recommend a toy", "CUST-1001", "adv-1")
    assert out["ok"] is False
    assert out["plan"] == ""
    assert out["used_tools"] == []
    assert "Gemini" in out["reply"] or "ADK" in out["reply"]


# --- Happy path: handle_advise parses the harness result (no network) ------ #
def test_handle_advise_parses_harness_result(monkeypatch):
    # Fake the COMMON harness's run() → handle_advise just parses the transcript.
    # No google import needed (the harness is stubbed), so this runs in CI too.
    result = AgentRunResult(
        ok=True,
        final_text="Try the Cheez-It at $3.49.",
        transcript=("/*PLANNING*/ step 1\n/*ACTION*/ search_inventory(snacks)\n"
                    "/*FINAL_ANSWER*/ Try the Cheez-It at $3.49."),
        used_tools=["search_inventory"],
        observations=[],
    )
    monkeypatch.setattr(adv._HARNESS, "run", lambda **k: result)
    out = handle_advise("a snack under $4", "CUST-1001", "adv-2")
    assert out["ok"] is True
    assert out["reply"] == "Try the Cheez-It at $3.49."
    assert "PLAN" in out["plan"]
    assert out["used_tools"] == ["search_inventory"]


# --- Endpoint wiring ------------------------------------------------------- #
def test_advise_endpoint_requires_auth():
    r = client.post("/advise", json={"message": "recommend a snack", "session_id": "x"})
    assert r.status_code == 401


def test_advise_endpoint_authorized(monkeypatch):
    # Force the graceful path so the test never needs a live Gemini call, but
    # still proves the route, schema, and auth all work end-to-end.
    monkeypatch.setattr(adv._HARNESS, "run",
                        lambda **k: AgentRunResult(ok=False, error="no adk"))
    monkeypatch.setattr(adv._HARNESS, "ready", lambda: False)
    token = client.post("/auth/login", json=GOOD).json()["access_token"]
    r = client.post(
        "/advise",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "a healthy snack under $4", "session_id": "adv-ep"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "unavailable"
    assert "plan" in body and "used_tools" in body
