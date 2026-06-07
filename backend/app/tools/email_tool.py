"""
Order-confirmation email — best-effort, never blocks an order.

Every placed order (single OR bulk; via text, voice, phone, camera vision, or an
uploaded Excel/CSV) funnels through `place_order` / `place_bulk_order`, which call
`send_order_email` here. Transport, first configured wins:
  1. SMTP        — set SMTP_HOST/SMTP_USER/SMTP_PASSWORD (e.g. Gmail app password)
  2. Resend API  — set RESEND_API_KEY (free tier)
  3. SIMULATED   — no creds → logged + reported in the reply (the demo default)

It is fully wrapped in try/except and returns a small dict — a mail failure can
NEVER break checkout. Recipient defaults to `settings.notify_email`.
"""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from ..observability.telemetry import incr, log_event


def _order_lines(order: dict) -> list[str]:
    """Human-readable item lines from a place_order / place_bulk_order result."""
    cart = order.get("cart") or []
    if cart:
        out = []
        for it in cart:
            opt = ", ".join(x for x in (it.get("color"), it.get("size")) if x)
            price = it.get("unit_price")
            line = f"- {it.get('name')}" + (f" ({opt})" if opt else "") + f" x{it.get('qty', 1)}"
            if price is not None:
                line += f"  @ ${float(price):.2f}"
            out.append(line)
        return out
    if order.get("items"):                       # bulk fallback (pre-formatted strings)
        return [f"- {s}" for s in order["items"]]
    if order.get("item"):
        return [f"- {order['item']}"]
    return []


def _build_email(order: dict) -> tuple[str, str]:
    """(subject, plaintext body) for an order confirmation."""
    oid = order.get("order_id", "—")
    total = order.get("total", 0) or 0
    eta = order.get("estimated_delivery", "")
    ful = order.get("fulfillment") or {}
    tracking = ful.get("tracking_number") or order.get("tracking_number") or ""
    n = len(order.get("cart") or order.get("items") or ([order["item"]] if order.get("item") else []))
    subject = f"GOOPHER — order {oid} confirmed (${float(total):.2f})"
    body = (
        f"Thanks for your order with GOOPHER!\n\n"
        f"Order:            {oid}\n"
        f"Items:            {n}\n"
        + "\n".join(_order_lines(order)) + "\n\n"
        f"Order total:      ${float(total):.2f}\n"
        + (f"Tracking:         {tracking}\n" if tracking else "")
        + (f"Est. delivery:    {eta}\n" if eta else "")
        + "\nWe'll let you know when it ships.\n— GOOPHER"
    )
    return subject, body


def send_order_email(order: dict, to: Optional[str] = None) -> dict:
    """Send an order-confirmation email. Best-effort: returns
    {sent, mode, to, detail} and NEVER raises."""
    settings = get_settings()
    to = to or settings.notify_email
    result = {"sent": False, "mode": "disabled", "to": to, "detail": ""}
    if not settings.email_enabled or not to:
        return result
    try:
        subject, body = _build_email(order)
        if settings.smtp_host and settings.smtp_user and settings.smtp_password:
            _send_smtp(settings, to, subject, body)
            result.update(sent=True, mode="smtp")
        elif settings.resend_api_key:
            _send_resend(settings, to, subject, body)
            result.update(sent=True, mode="resend")
        else:
            # No transport configured — simulate (so the flow + demo still work).
            result.update(sent=False, mode="simulated",
                          detail="no SMTP/Resend creds set; email simulated")
            log_event("order_email_simulated", to=to, order_id=order.get("order_id"),
                      subject=subject)
        incr("order_emails_total")
        log_event("order_email", to=to, order_id=order.get("order_id"), mode=result["mode"])
    except Exception as exc:  # noqa: BLE001 - mail must never break checkout
        result.update(sent=False, mode="error", detail=str(exc)[:200])
        log_event("order_email_failed", to=to, reason=str(exc))
    return result


def _send_smtp(settings, to: str, subject: str, body: str) -> None:
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.sendmail(settings.smtp_user, [to], msg.as_string())


def _send_resend(settings, to: str, subject: str, body: str) -> None:
    import json
    import urllib.request

    payload = json.dumps({
        "from": settings.email_from or "GOOPHER <onboarding@resend.dev>",
        "to": [to], "subject": subject, "text": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": f"Bearer {settings.resend_api_key}",
                 "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
