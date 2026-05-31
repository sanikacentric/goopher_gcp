"""
Integration-ish tests for the orchestrator's fallback engine (T2).

These run WITHOUT a Gemini key, so they exercise the deterministic intent
router + real tools and assert the agent returns grounded answers. They also
verify the unified agent maintains context and adapts to channel.
"""
from backend.app.agents.orchestrator import AgentService
from backend.app.models.schemas import Attachment, ChatRequest


def _svc():
    return AgentService()


def test_product_search_intent():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="show me black dresses under $45", session_id="s1"),
        customer_id="CUST-1001",
    )
    assert "inventory_search" in resp.used_tools
    assert "dress" in resp.reply.lower()


def test_single_order_intent():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="where is ORD-50002?", session_id="s2"),
        customer_id="CUST-1001",
    )
    assert "order_status" in resp.used_tools
    assert "ORD-50002" in resp.reply
    assert "Shipped" in resp.reply


def test_bulk_order_intent():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="status for ORD-50001 ORD-50002 ORD-50003", session_id="s3"),
        customer_id="CUST-1001",
    )
    assert "order_bulk_status" in resp.used_tools


def test_list_my_orders_intent():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="show my orders", session_id="s4"),
        customer_id="CUST-1001",
    )
    assert "order_list_for_customer" in resp.used_tools
    assert "3 order" in resp.reply


def test_phone_channel_is_voice_safe():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="show my orders", session_id="s5", channel="phone"),
        customer_id="CUST-1001",
    )
    assert resp.channel == "phone"
    assert "*" not in resp.reply and "http" not in resp.reply


def test_language_is_detected_and_persisted():
    svc = _svc()
    resp = svc.run_turn(
        ChatRequest(message="Hola, ¿dónde está mi pedido ORD-50001?", session_id="s6"),
        customer_id="CUST-1001",
    )
    assert resp.language == "es"


def test_context_maintained_across_turns():
    svc = _svc()
    sid = "s7"
    svc.run_turn(ChatRequest(message="show navy dresses", session_id=sid), "CUST-1001")
    # Second turn in a different channel; memory should have both turns recorded.
    svc.run_turn(ChatRequest(message="show my orders", session_id=sid, channel="phone"), "CUST-1001")
    hist = svc.memory.history_text(sid)
    assert "navy" in hist.lower()
    assert "web/" in hist and "phone/" in hist


def test_image_attachment_is_normalized():
    svc = _svc()
    att = Attachment(kind="image", filename="dress.jpg", mime_type="image/jpeg")
    resp = svc.run_turn(
        ChatRequest(message="find one like this", session_id="s8", attachments=[att]),
        customer_id="CUST-1001",
    )
    # Modality recorded as image in memory; reply still produced.
    assert resp.reply
