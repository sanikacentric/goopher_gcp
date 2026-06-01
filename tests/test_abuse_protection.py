"""
Tests for abuse protection: request-size limits, message-length cap, and
per-client rate limiting (DoS / cost-DoS guard).
"""
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app

client = TestClient(app)
settings = get_settings()

GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}


def _token() -> str:
    return client.post("/auth/login", json=GOOD).json()["access_token"]


def test_oversized_body_rejected():
    """A body larger than max_request_bytes is rejected with 413 by middleware."""
    token = _token()
    big = "x" * (settings.max_request_bytes + 1024)
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": big, "session_id": "oversize"},
    )
    assert r.status_code == 413


def test_overlong_message_rejected():
    """A message over max_chat_message_chars is rejected with 413 by the route."""
    token = _token()
    msg = "a" * (settings.max_chat_message_chars + 1)
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": msg, "session_id": "longmsg"},
    )
    assert r.status_code == 413


def test_chat_rate_limit_triggers_429(monkeypatch):
    """Exceeding the per-client /chat budget returns 429."""
    # Tighten the chat limit to 3/min for this test only.
    monkeypatch.setattr(settings, "rate_limit_chat_per_min", 3)
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    body = {"message": "where is ORD-50002?", "session_id": "rl"}

    codes = [
        client.post("/chat", headers=headers, json=body).status_code
        for _ in range(6)
    ]
    # At least one request beyond the budget must be rate-limited.
    assert 429 in codes, codes


def test_healthz_not_rate_limited(monkeypatch):
    """Health checks are exempt from rate limiting (Cloud Run probes them)."""
    monkeypatch.setattr(settings, "rate_limit_global_per_min", 1)
    codes = [client.get("/healthz").status_code for _ in range(5)]
    assert all(c == 200 for c in codes), codes
