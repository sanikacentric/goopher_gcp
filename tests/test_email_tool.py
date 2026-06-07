"""
Tests for the order-confirmation email (best-effort, never blocks an order).

Transport is stubbed — no real email is sent. We verify: simulated mode with no
creds, the SMTP and Resend paths when configured, that a mail failure never
raises, and that place_order/place_bulk_order attach the email status.
"""
import types

import backend.app.tools.email_tool as et
from backend.app.tools.checkout_tool import place_bulk_order, place_order


def _settings(**over):
    base = dict(email_enabled=True, notify_email="tungaresanika2@gmail.com",
                email_from="GOOPHER <orders@goopher.app>", smtp_host="", smtp_port=587,
                smtp_user="", smtp_password="", resend_api_key="")
    base.update(over)
    return types.SimpleNamespace(**base)


ORDER = {
    "order_id": "ORD-1", "total": 12.5, "estimated_delivery": "2026-06-08",
    "cart": [{"name": "Oreo", "color": "Original", "size": "18oz", "qty": 2, "unit_price": 3.99}],
    "fulfillment": {"tracking_number": "UPS123"},
}


def test_simulated_when_no_transport(monkeypatch):
    monkeypatch.setattr(et, "get_settings", lambda: _settings())
    r = et.send_order_email(ORDER)
    assert r["sent"] is False and r["mode"] == "simulated"
    assert r["to"] == "tungaresanika2@gmail.com"


def test_smtp_path_used_when_configured(monkeypatch):
    monkeypatch.setattr(et, "get_settings",
                        lambda: _settings(smtp_host="smtp.x", smtp_user="u", smtp_password="p"))
    captured = {}
    monkeypatch.setattr(et, "_send_smtp",
                        lambda s, to, sub, body: captured.update(to=to, sub=sub, body=body))
    r = et.send_order_email(ORDER)
    assert r["sent"] is True and r["mode"] == "smtp"
    assert captured["to"] == "tungaresanika2@gmail.com"
    assert "ORD-1" in captured["sub"] and "Oreo" in captured["body"]


def test_resend_path_used_when_configured(monkeypatch):
    monkeypatch.setattr(et, "get_settings", lambda: _settings(resend_api_key="re_x"))
    called = {}
    monkeypatch.setattr(et, "_send_resend", lambda s, to, sub, body: called.update(to=to))
    r = et.send_order_email(ORDER)
    assert r["sent"] is True and r["mode"] == "resend" and called["to"]


def test_mail_failure_never_raises(monkeypatch):
    monkeypatch.setattr(et, "get_settings",
                        lambda: _settings(smtp_host="smtp.x", smtp_user="u", smtp_password="p"))
    def boom(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(et, "_send_smtp", boom)
    r = et.send_order_email(ORDER)
    assert r["sent"] is False and r["mode"] == "error"   # caught, not raised


def test_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr(et, "get_settings", lambda: _settings(email_enabled=False))
    assert et.send_order_email(ORDER)["mode"] == "disabled"


def test_localize_callable_translates_subject_and_body(monkeypatch):
    """A non-English order passes a localize callable → the email is translated."""
    monkeypatch.setattr(et, "get_settings",
                        lambda: _settings(smtp_host="smtp.x", smtp_user="u", smtp_password="p"))
    cap = {}
    monkeypatch.setattr(et, "_send_smtp", lambda s, to, sub, body: cap.update(sub=sub, body=body))
    r = et.send_order_email(ORDER, localize=lambda s: "[ES] " + s)
    assert r["sent"] and cap["sub"].startswith("[ES] ") and cap["body"].startswith("[ES] ")


def test_localize_failure_falls_back_and_still_sends(monkeypatch):
    """If translation throws, the email still sends in English (never blocks)."""
    monkeypatch.setattr(et, "get_settings",
                        lambda: _settings(smtp_host="smtp.x", smtp_user="u", smtp_password="p"))
    cap = {}
    monkeypatch.setattr(et, "_send_smtp", lambda s, to, sub, body: cap.update(sub=sub))
    def boom(_s):
        raise RuntimeError("translate down")
    r = et.send_order_email(ORDER, localize=boom)
    assert r["sent"] and "ORD-1" in cap["sub"]   # fell back to the English subject


# --- orders attach the email status (every path goes through these) --------- #
def test_place_order_attaches_email():
    res = place_order("CUST-1001")
    assert res["ok"] and "email" in res and res["email"]["to"] == "tungaresanika2@gmail.com"


def test_place_bulk_order_attaches_email():
    res = place_bulk_order("CUST-1001")
    assert res["ok"] and "email" in res and res["email"]["to"]
