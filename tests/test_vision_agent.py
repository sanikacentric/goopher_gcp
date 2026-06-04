"""
Tests for the NEW Vision subagent ("see it, shop it") and POST /vision.

Recognition (the Gemini Vision call) is monkeypatched so the tests are hermetic
and need no camera, network, or API key — we exercise the resolve→act logic.
"""
import base64

import backend.app.agents.vision_agent as va
from backend.app.agents.vision_agent import handle_vision
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
GOOD = {"email": "demo@goopher.app", "password": "test-master-password"}
FAKE_IMG = base64.b64encode(b"not-a-real-image").decode()


def _mock_recognize(label):
    return lambda image_b64, mime_type: (label, "gemini-vision")


def test_vision_price_intent_answers_price(monkeypatch):
    monkeypatch.setattr(va, "_recognize", _mock_recognize("soccer ball"))
    out = handle_vision("what is the price of this?", FAKE_IMG, "image/jpeg",
                        "CUST-1001", "vis-1")
    assert out["checkout"] is None
    assert out["recognized"]["matched"] is True
    assert "$" in out["reply"]
    assert "soccer" in out["reply"].lower()


def test_vision_order_intent_previews_and_asks_to_confirm(monkeypatch):
    # Vision now PREVIEWS the order (confirm=False) and asks to confirm — it does
    # NOT charge immediately — identical to the text/voice flow.
    monkeypatch.setattr(va, "_recognize", _mock_recognize("oreo cookies"))
    out = handle_vision("place an order", FAKE_IMG, "image/jpeg",
                        "CUST-1001", "vis-2")
    assert out["checkout"] and out["checkout"]["pending"] is True
    assert out["checkout"]["cart"]                 # structured cart preview
    assert out["checkout"].get("confirm_text")     # carried for the Confirm button
    assert "oreo" in out["reply"].lower()
    assert "confirm" in out["reply"].lower()       # asks before placing
    assert "checkout_agent" in out["used_tools"]


def test_vision_unrecognized_item_is_not_substituted(monkeypatch):
    monkeypatch.setattr(va, "_recognize", _mock_recognize("ceramic garden gnome"))
    out = handle_vision("buy this", FAKE_IMG, "image/jpeg", "CUST-1001", "vis-3")
    assert out["checkout"] is None
    assert out["recognized"]["matched"] is False
    assert "don't carry" in out["reply"].lower() or "do not carry" in out["reply"].lower()


def test_vision_recognition_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(va, "_recognize", lambda b, m: ("", "none"))
    out = handle_vision("place an order", FAKE_IMG, "image/jpeg", "CUST-1001", "vis-4")
    assert out["checkout"] is None
    assert out["recognized"] is None
    assert "couldn't" in out["reply"].lower() or "could not" in out["reply"].lower()


def test_vision_endpoint_requires_auth():
    r = client.post("/vision", json={"image_b64": FAKE_IMG, "session_id": "x"})
    assert r.status_code == 401


def test_vision_endpoint_order_flow(monkeypatch):
    monkeypatch.setattr(va, "_recognize", _mock_recognize("LEGO bricks"))
    token = client.post("/auth/login", json=GOOD).json()["access_token"]
    r = client.post(
        "/vision",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "place an order", "image_b64": FAKE_IMG,
              "mime_type": "image/jpeg", "session_id": "vis-ep"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["checkout"] and body["checkout"]["pending"] is True
    assert body["checkout"].get("confirm_text")
    assert "lego" in body["reply"].lower()
    assert "confirm" in body["reply"].lower()


def test_vision_confirm_round_trip_places_the_same_item(monkeypatch):
    """Vision previews → the Confirm button re-sends confirm_text to /chat with
    confirm=True → exactly the recognized item is placed (no substitution)."""
    monkeypatch.setattr(va, "_recognize", _mock_recognize("oreo cookies"))
    token = client.post("/auth/login", json=GOOD).json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    # 1) Vision returns a PREVIEW (nothing charged yet).
    r1 = client.post("/vision", headers=hdr, json={
        "question": "place an order", "image_b64": FAKE_IMG,
        "mime_type": "image/jpeg", "session_id": "vis-cf"})
    pending = r1.json()["checkout"]
    assert pending["pending"] is True
    confirm_text = pending["confirm_text"]
    # 2) Confirm → exactly what the extension does on the Confirm button.
    r2 = client.post("/chat", headers=hdr, json={
        "message": confirm_text, "session_id": "vis-cf", "confirm": True})
    body = r2.json()
    assert body["checkout"] and body["checkout"]["ok"] is True
    assert "oreo" in body["reply"].lower()
