"""High-volume scale-simulation endpoints (/sim/*) — read-only, no LLM, no writes."""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_sim_chat_browse_is_readonly_and_routes():
    r = client.get("/sim/chat", params={"message": "oreo cookies", "mode": "browse"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["sim"] is True
    assert body["routed_to"] == "inventory_agent"
    assert "matches" in body and body["served"] >= 1


def test_sim_chat_order_status_mode():
    r = client.get("/sim/chat", params={"mode": "order_status"})
    assert r.status_code == 200
    body = r.json()
    assert body["routed_to"] == "order_agent" and "orders" in body


def test_sim_chat_post_also_works():
    assert client.post("/sim/chat", params={"message": "lego"}).status_code == 200


def test_sim_stats_reports_volume():
    r = client.get("/sim/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["products"] > 0 and s["variants"] > 0
    assert s["departments"] and "sim_requests_served" in s
    assert "model" in s and "backend" in s


def test_sim_counter_increments():
    before = client.get("/sim/stats").json()["sim_requests_served"]
    client.get("/sim/chat", params={"message": "chips"})
    after = client.get("/sim/stats").json()["sim_requests_served"]
    assert after >= before + 1


def test_sim_disabled_returns_404(monkeypatch):
    from backend.app import main as m
    monkeypatch.setattr(m.settings, "scale_sim_enabled", False)
    assert client.get("/sim/chat").status_code == 404
    assert client.get("/sim/stats").status_code == 404
