"""
Tests for the self-healing Guardian agent (isolated — touches no real flow).
"""
from fastapi.testclient import TestClient

from backend.app.agents.guardian import Guardian
from backend.app.main import app

client = TestClient(app)


def test_healthy_runs_on_primary():
    g = Guardian()
    out = g.simulate("vertex")
    assert out["result"]["served_by"] == "primary"
    assert g.health()["components"]["vertex"]["state"] == "healthy"


def test_chaos_triggers_failover_and_records_heal():
    g = Guardian()
    g.chaos.inject("vertex", "503")
    out = g.simulate("vertex")
    # Customer is still served — via the failover path.
    assert out["result"]["served_by"] == "failover"
    assert g.health()["components"]["vertex"]["state"] in ("healing", "down")
    assert g.health()["components"]["vertex"]["heals"] >= 1


def test_circuit_opens_then_heals_forward():
    g = Guardian()
    g.chaos.inject("catalog", "outage")
    g.simulate("catalog")
    g.simulate("catalog")                      # repeated failures → circuit opens
    assert g.health()["components"]["catalog"]["circuit"] == "open"
    # Fault cleared → probe heals forward to the primary.
    g.chaos.clear("catalog")
    g.tick()
    h = g.health()["components"]["catalog"]
    assert h["state"] == "healthy" and h["circuit"] == "closed"


def test_dev_endpoints_health_chaos_heal():
    # health
    h = client.get("/dev/health").json()
    assert "components" in h and "vertex" in h["components"]
    # inject chaos → run a synthetic request → component degrades, customer served
    client.post("/dev/chaos", json={"component": "vertex", "action": "inject"})
    sim = client.post("/dev/heal-demo", json={"component": "vertex"}).json()
    assert sim["ok"] and sim["result"]["served_by"] == "failover"
    # clearing chaos heals it forward
    after = client.post("/dev/chaos", json={"component": "vertex", "action": "clear"}).json()
    assert after["components"]["vertex"]["state"] == "healthy"


def test_guardian_does_not_touch_real_chat():
    """Sanity: a normal chat turn still works with Guardian present."""
    tok = client.post("/auth/login",
                      json={"email": "demo@goopher.app", "password": "test-master-password"}
                      ).json()["access_token"]
    r = client.post("/chat", headers={"Authorization": f"Bearer {tok}"},
                    json={"message": "do you have oreos", "session_id": "g-iso"})
    assert r.status_code == 200
