"""
End-to-end API tests via FastAPI TestClient (T1 auth + /chat + /orders/bulk).
"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


# Single-user lockdown: allowlisted email + master password (set in conftest).
GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}


def _token() -> str:
    r = client.post("/auth/login", json=GOOD)
    assert r.status_code == 200
    return r.json()["access_token"]


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_success():
    r = client.post("/auth/login", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body["customer"]["customer_id"] == "CUST-1001"


def test_login_wrong_password():
    r = client.post("/auth/login", json={"email": "demo@goopher.app", "password": "bad"})
    assert r.status_code == 401


def test_login_non_allowlisted_email_rejected():
    # Correct master password, but a non-allowlisted email -> denied.
    r = client.post("/auth/login",
                    json={"email": "attacker@evil.com", "password": "test-master-password"})
    assert r.status_code == 401


def test_chat_requires_auth():
    r = client.post("/chat", json={"message": "hi", "session_id": "x"})
    assert r.status_code == 401


def test_chat_happy_path():
    token = _token()
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "where is ORD-50002?", "session_id": "api-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "ORD-50002" in body["reply"]
    assert body["session_id"] == "api-1"


def test_bulk_orders_endpoint():
    token = _token()
    r = client.post(
        "/orders/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={"order_ids": ["ORD-50001", "ORD-50002", "ORD-NOPE"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["found"] == 2
    assert "ORD-NOPE" in body["missing"]


def test_orders_mine_requires_auth():
    assert client.get("/orders/mine").status_code == 401


def test_orders_mine_lists_customer_orders_including_new():
    """The cart/orders panel endpoint returns the customer's orders, and a newly
    placed order shows up in it."""
    token = _token()
    h = {"Authorization": f"Bearer {token}"}
    before = client.get("/orders/mine", headers=h).json()["count"]
    # Checkout is two-step: preview, then confirm to actually place it.
    prev = client.post("/chat", headers=h,
                       json={"message": "place an order of oreo cookies", "session_id": "mine-1"})
    assert prev.json()["checkout"]["pending"] is True
    client.post("/chat", headers=h,
                json={"message": "place an order of oreo cookies", "session_id": "mine-1",
                      "confirm": True})
    after = client.get("/orders/mine", headers=h).json()
    assert after["count"] >= before + 1
    # Each order carries the fields the panel renders.
    o = after["orders"][0]
    assert "order_id" in o and "items" in o and "total" in o


def test_version_endpoint():
    r = client.get("/version")
    assert r.status_code == 200
    assert "build" in r.json()


def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "chat_requests_total" in r.json()["metrics"]
