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


def test_chaos_triggers_failover_then_restores():
    g = Guardian()
    g.chaos.inject("vertex", "503")
    out = g.simulate("vertex")
    # Customer is still served — via the failover path during the heal.
    assert out["result"]["served_by"] == "failover"
    h = g.health()["components"]["vertex"]
    # The staged heal recovers and heals forward → restored to healthy.
    assert h["heals"] >= 1
    assert h["state"] == "healthy" and h["circuit"] == "closed"
    assert g.chaos.active("vertex") is None     # fault cleared as it healed forward


def test_repeatable_kill_heal():
    """Each kill→heal cycle works (the breaker reset on a fresh fault means the
    full heal runs every time, not a silent short-circuit)."""
    g = Guardian()
    for _ in range(3):
        g._reset_circuit("catalog")
        g.chaos.inject("catalog", "outage")
        out = g.simulate("catalog")
        assert out["result"]["served_by"] == "failover"
        assert g.health()["components"]["catalog"]["state"] == "healthy"


def test_dev_endpoints_health_chaos_heal():
    # health
    h = client.get("/dev/health").json()
    assert "components" in h and "vertex" in h["components"]
    # inject chaos → run a synthetic request → customer served via failover, then
    # the staged heal restores the component.
    client.post("/dev/chaos", json={"component": "vertex", "action": "inject"})
    sim = client.post("/dev/heal-demo", json={"component": "vertex"}).json()
    assert sim["ok"] and sim["result"]["served_by"] == "failover"
    assert sim["health"]["components"]["vertex"]["state"] == "healthy"


def test_guardian_does_not_touch_real_chat():
    """Sanity: a normal chat turn still works with Guardian present."""
    tok = client.post("/auth/login",
                      json={"email": "demo@goopher.app", "password": "test-master-password"}
                      ).json()["access_token"]
    r = client.post("/chat", headers={"Authorization": f"Bearer {tok}"},
                    json={"message": "do you have oreos", "session_id": "g-iso"})
    assert r.status_code == 200
