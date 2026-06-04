"""Tests for the Developer Portal flow visualizer endpoints."""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)
GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}


def test_dev_page_served():
    r = client.get("/dev")
    assert r.status_code == 200
    assert "Developer Portal" in r.text


def test_dev_recent_empty_ok():
    r = client.get("/dev/recent")
    assert r.status_code == 200
    assert "records" in r.json()


def test_flow_captured_after_turn():
    """A login + chat must produce a 'login' and a 'turn' flow record with the
    full pipeline of stages: auth → session → preprocess → orchestrator → tool
    → memory."""
    token = client.post("/auth/login", json=GOOD).json()["access_token"]
    client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "do you have oreos", "session_id": "devtest"},
    )
    recs = client.get("/dev/recent").json()["records"]
    kinds = {r["kind"] for r in recs}
    assert "login" in kinds and "turn" in kinds

    turn = [r for r in recs if r["kind"] == "turn" and r["session_id"] == "devtest"][-1]
    stages = {s["stage"] for s in turn["steps"]}
    # The end-to-end pipeline the portal visualizes:
    assert {"auth", "session", "preprocess", "orchestrator", "tool", "memory"} <= stages
    assert turn["used_tools"]  # at least one tool ran
    assert "history_preview" in turn["memory"]


def test_fulfillment_pipeline_is_one_record_not_duplicated():
    """A fulfillment pipeline commits once per stage as it advances. The portal
    must show it as ONE record (deduped by id), not one card per stage."""
    import os
    os.environ["FULFILLMENT_STAGE_DELAY"] = "0"
    from backend.app.observability.flow_recorder import get_recorder
    from backend.app.tools.checkout_tool import place_order

    rec = get_recorder()
    before_ver = rec.current_version()
    result = place_order("CUST-1001")          # runs the 9-stage pipeline
    order_id = result["order_id"]

    ful = [r for r in rec.recent(limit=100)
           if r["kind"] == "fulfillment" and r["order_id"] == order_id]
    assert len(ful) == 1                        # exactly one record, not nine
    assert len(ful[0]["steps"]) == 9            # all stages merged into it

    # The live stream (since a version) also yields each record id once.
    changed_ids = [r["id"] for r in rec.since(before_ver) if r["kind"] == "fulfillment"]
    assert len(set(changed_ids)) == len(changed_ids)


def test_duplicate_turn_within_window_collapses_to_one_card():
    """An identical turn (same session + same question) recorded again within the
    window — e.g. a cold-start resend — must merge onto ONE card, not duplicate."""
    import time
    from backend.app.observability.flow_recorder import FlowRecord, get_recorder

    rec = get_recorder()
    t = time.time()
    msg = "what is the price of oreo?"
    rec.add(FlowRecord(id=rec.next_id(), ts=t, kind="turn",
                       session_id="dup-A", user_message=msg, reply="$3.99"))
    rec.add(FlowRecord(id=rec.next_id(), ts=t + 27, kind="turn",
                       session_id="dup-A", user_message=msg, reply="$3.99"))
    turns = [x for x in rec.recent(100)
             if x["kind"] == "turn" and x["session_id"] == "dup-A"]
    assert len(turns) == 1                      # collapsed onto one card

    # A re-ask LONG after the window is a separate, legitimate card.
    rec.add(FlowRecord(id=rec.next_id(), ts=t + 500, kind="turn",
                       session_id="dup-A", user_message=msg, reply="$3.99"))
    turns = [x for x in rec.recent(100)
             if x["kind"] == "turn" and x["session_id"] == "dup-A"]
    assert len(turns) == 2


def test_distinct_questions_are_not_collapsed():
    import time
    from backend.app.observability.flow_recorder import FlowRecord, get_recorder

    rec = get_recorder()
    t = time.time()
    rec.add(FlowRecord(id=rec.next_id(), ts=t, kind="turn",
                       session_id="dup-B", user_message="price of oreo?", reply="a"))
    rec.add(FlowRecord(id=rec.next_id(), ts=t + 2, kind="turn",
                       session_id="dup-B", user_message="price of chips?", reply="b"))
    turns = [x for x in rec.recent(100)
             if x["kind"] == "turn" and x["session_id"] == "dup-B"]
    assert len(turns) == 2                      # different questions → two cards
