"""
Unit tests for memory (T3 / context) and the three subagents
(channel 2A-4, language 2A-5, modality 2A-6).
"""
from backend.app.agents import channel_agent, language_agent, modality_agent
from backend.app.memory.memory_agent import Turn, get_memory_store
from backend.app.models.schemas import Attachment


# ---- Memory / context preservation ----
def test_memory_preserves_context_across_switches():
    store = get_memory_store()
    sid = "sess-test-1"
    store.add_turn(sid, Turn(role="user", content="show navy dresses", channel="web", language="en"))
    store.remember(sid, "last_color", "Navy")
    # Switch channel + language; memory must still hold the fact.
    store.add_turn(sid, Turn(role="user", content="¿y en negro?", channel="phone", language="es"))
    assert store.recall(sid, "last_color") == "Navy"
    hist = store.history_text(sid)
    assert "web/en" in hist and "phone/es" in hist


# ---- Language subagent ----
def test_detect_spanish():
    assert language_agent.detect_language("Hola, ¿dónde está mi pedido?") == "es"


def test_detect_english_default():
    assert language_agent.detect_language("where is my order") == "en"


def test_english_overrides_sticky_non_english_default():
    """A clearly-English message must return 'en' even when the session's
    remembered (default) language is Spanish — no language stickiness."""
    assert language_agent.detect_language("place an order of above 10 oreos",
                                          default="es") == "en"
    assert language_agent.detect_language("order it", default="es") == "en"
    # But a genuinely Spanish message still detects as Spanish.
    assert language_agent.detect_language("el precio del vestido", default="en") == "es"


def test_language_directive():
    d = language_agent.language_directive("es")
    assert "Spanish" in d


# ---- Channel subagent ----
def test_phone_directive_mentions_voice():
    assert "PHONE" in channel_agent.channel_directive("phone")


def test_adapt_for_phone_strips_markdown():
    web = "**Order ORD-50002** is *Shipped*. [Track](http://x.com)"
    spoken = channel_agent.adapt_for_phone(web)
    assert "*" not in spoken and "http" not in spoken and "Track" in spoken


# ---- Modality subagent ----
def test_classify_modality_image():
    atts = [Attachment(kind="image", filename="dress.jpg", mime_type="image/jpeg")]
    assert modality_agent.classify_modality("", atts) == "image"


def test_extract_order_ids_from_text():
    ids = modality_agent.extract_order_ids_from_text("check ORD-50001 and ORD-50002 please")
    assert ids == ["ORD-50001", "ORD-50002"]


def test_extract_order_ids_from_file():
    import base64
    csv_bytes = b"order_id\nORD-50001\nORD-50003\n"
    att = Attachment(kind="file", filename="orders.csv", mime_type="text/csv",
                     content_b64=base64.b64encode(csv_bytes).decode())
    ids = modality_agent.extract_order_ids_from_file(att)
    assert "ORD-50001" in ids and "ORD-50003" in ids
