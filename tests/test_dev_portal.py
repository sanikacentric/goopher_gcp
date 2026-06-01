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
