"""Tests for the checkout flow (Req 4: place an order)."""
from backend.app.agents.orchestrator import AgentService
from backend.app.db.database import get_repository
from backend.app.models.schemas import ChatRequest
from backend.app.tools.checkout_tool import (
    add_to_cart,
    place_bulk_order,
    place_order,
    process_payment,
    resolve_variant_by_name,
)


def test_add_to_cart_defaults_to_in_stock():
    res = add_to_cart()
    assert res["ok"] is True
    assert res["cart"]["qty"] == 1
    assert res["subtotal"] > 0


def test_process_payment_always_succeeds():
    res = process_payment(29.99, method="card")
    assert res["ok"] is True
    assert res["status"] == "SUCCESS"
    assert res["transaction_id"].startswith("PAY-")


def test_place_order_persists_new_order():
    repo = get_repository()
    before = {o.order_id for o in repo.list_orders_for_customer("CUST-1001")}
    res = place_order("CUST-1001")
    assert res["ok"] is True
    assert res["order_id"].startswith("ORD-")
    assert res["payment"]["status"] == "SUCCESS"
    after = {o.order_id for o in repo.list_orders_for_customer("CUST-1001")}
    assert res["order_id"] in after and res["order_id"] not in before


def test_place_an_order_intent_routes_to_checkout():
    svc = AgentService()
    resp = svc.run_turn(
        ChatRequest(message="place an order", session_id="chk-intent"),
        customer_id="CUST-1001",
    )
    assert "checkout_agent" in resp.used_tools
    assert "placed" in resp.reply.lower() or "order" in resp.reply.lower()


def test_checkout_turn_records_skill_layer_in_dev_portal():
    """The deterministic checkout path should still surface the checkout SKILL +
    its tools in the dev portal (skill/tool parity with the ADK path)."""
    from backend.app.observability.flow_recorder import _recorder

    AgentService().run_turn(
        ChatRequest(message="place an order", session_id="chk-portal"),
        customer_id="CUST-1001",
    )
    # NB: placing an order also commits a separate "fulfillment" record, so scan
    # recent records for the checkout TURN that carries the checkout skill step.
    recs = _recorder.recent(20)
    skill_steps = [s for r in recs for s in r["steps"]
                   if s["stage"] == "skill" and "checkout" in s["name"]]
    assert skill_steps, "checkout path did not record a checkout skill step"
    assert any("transactional" in s["detail"] for s in skill_steps)


def test_resolve_variant_by_name_finds_named_product():
    """Ordering by product name resolves to that product's in-stock variant."""
    res = resolve_variant_by_name("oreo cookies")
    assert res["ok"] is True
    assert "oreo" in res["product"].lower()
    assert res["variant_id"]


def test_resolve_variant_by_name_never_substitutes():
    """An unknown product is refused — NOT swapped for a different item."""
    res = resolve_variant_by_name("flying spaghetti monster plushie")
    assert res["ok"] is False
    assert res.get("not_found") is True
    assert "variant_id" not in res
    assert "substitut" in res["message"].lower()


def test_named_order_buys_that_product_not_a_substitute():
    """'place an order of oreo cookies' must order Oreo, never a fallback item."""
    svc = AgentService()
    resp = svc.run_turn(
        ChatRequest(message="place an order of oreo cookies", session_id="chk-named"),
        customer_id="CUST-1001",
    )
    assert "checkout_agent" in resp.used_tools
    assert resp.checkout and resp.checkout.get("ok") is True
    items = " ".join(resp.checkout.get("items", [])).lower()
    assert "oreo" in items
    assert "cheez" not in items  # no silent substitution


def test_named_order_unknown_product_does_not_place_order():
    """Naming a product that isn't in the catalog places NO order (no substitute)."""
    svc = AgentService()
    resp = svc.run_turn(
        ChatRequest(message="place an order of flying unicorn slippers",
                    session_id="chk-unknown"),
        customer_id="CUST-1001",
    )
    assert resp.checkout is not None and resp.checkout.get("ok") is False
    assert resp.checkout.get("order_id") is None


def test_checkout_is_structured_even_with_adk_path_on(monkeypatch):
    """In the cloud the ADK path is on, but checkout must STILL be handled
    deterministically: the reply is the cart receipt and resp.checkout is set.
    (Regression: previously checkout went through the ADK agent, which phrased
    its own reply and never populated the cart/checkout payload.)"""
    import backend.app.agents.orchestrator as orch
    monkeypatch.setattr(orch._settings, "use_adk_path", True, raising=False)
    svc = AgentService()
    resp = svc.run_turn(
        ChatRequest(message="place an order of oreo cookies", session_id="adk-chk"),
        customer_id="CUST-1001",
    )
    assert "checkout_agent" in resp.used_tools
    assert resp.checkout and resp.checkout.get("ok") is True
    assert resp.checkout.get("cart")                      # structured cart present
    assert "🛒 Your cart" in resp.reply                   # deterministic receipt
    assert "oreo" in resp.reply.lower()


def test_checkout_previews_then_confirms():
    """Two-step checkout: a preview (no order placed) → confirm (places it)."""
    from backend.app.db.database import get_repository
    repo = get_repository()
    svc = AgentService()
    before = len(repo.list_orders_for_customer("CUST-1001"))
    # Preview — nothing charged/placed.
    prev = svc._try_checkout("place an order of oreo cookies", "CUST-1001", confirm=False)
    assert svc._last_checkout.get("pending") is True
    assert "confirm" in prev[0].lower()
    assert len(repo.list_orders_for_customer("CUST-1001")) == before   # nothing placed
    # Confirm — now it places.
    done = svc._try_checkout("place an order of oreo cookies", "CUST-1001", confirm=True)
    assert svc._last_checkout.get("ok") is True and not svc._last_checkout.get("pending")
    assert "ORDER PLACED" in done[0]
    assert len(repo.list_orders_for_customer("CUST-1001")) == before + 1


def test_contextual_order_uses_last_viewed_not_a_stray_number():
    """'order above 10 items' after looking at Oreos orders 10 OREOS — not a
    product whose NAME happens to contain '10' (the qty must not leak into the
    product search), and 'above' resolves to the last-viewed item."""
    from backend.app.tools.inventory_tool import search_inventory
    svc = AgentService()
    search_inventory(query="oreo cookies")          # shopper views Oreos
    out = svc._try_checkout("can u place an order of above 10 items", "CUST-1001")
    assert out is not None
    pay = svc._last_checkout
    assert pay and pay.get("ok") is True
    line = pay["cart"][0]
    assert "oreo" in line["name"].lower()           # NOT play-doh
    assert line["qty"] == 10
    # "order it" resolves to whatever was viewed most recently.
    search_inventory(query="lego")
    out2 = svc._try_checkout("order it", "CUST-1001")
    assert "lego" in svc._last_checkout["cart"][0]["name"].lower()


def test_bulk_order_of_named_product_not_default_basket():
    """'bulk order of classic potato chips' orders THAT product in bulk, not a
    random default basket."""
    svc = AgentService()
    out = svc._try_checkout("bulk order of classic potato chips", "CUST-1001")
    assert out is not None
    cart = svc._last_checkout["cart"]
    assert len(cart) == 1
    assert "potato chips" in cart[0]["name"].lower()
    assert cart[0]["qty"] >= 10                       # "bulk" ⇒ ≥10


def test_natural_phrasing_order_triggers_structured_checkout():
    """Conversational order phrasings (not just "place an order") must hit the
    structured gate so the cart payload is produced — and status queries must
    NOT be mistaken for purchases."""
    svc = AgentService()
    # Purchase intents → structured checkout with a cart.
    for msg in ["hi can you please order balls for me", "get me a lego",
                "i want to buy oreos"]:
        svc._last_checkout = None
        out = svc._try_checkout(msg, "CUST-1001")
        assert out is not None, msg
        assert svc._last_checkout and svc._last_checkout.get("ok") is True
        assert svc._last_checkout.get("cart")
    # Status / inventory queries → NOT checkout.
    for msg in ["where is ORD-50019", "what are my orders", "is the lego in stock",
                "track my order"]:
        assert svc._try_checkout(msg, "CUST-1001") is None, msg


def test_typed_product_sku_resolves_not_substitutes():
    """Typing a product SKU (not a full variant_id) orders that product, never
    a fallback item."""
    svc = AgentService()
    resp = svc.run_turn(
        ChatRequest(message="place an order of TOY-LEG-3002", session_id="sku-chk"),
        customer_id="CUST-1001",
    )
    assert resp.checkout and resp.checkout.get("ok") is True
    assert "lego" in resp.reply.lower()


def test_order_from_uploaded_file_places_structured_bulk_order():
    """Attaching an order file + asking to order it parses the file into a
    structured bulk order with per-line quantities; unknown items are skipped,
    never substituted."""
    import base64
    from backend.app.models.schemas import Attachment
    svc = AgentService()
    # "order - N product" is the real-world format the demo file uses.
    order_txt = ("order - 2 soccer balls\norder -3 oreos\nlego x1\n"
                 "TOY-NRF-3003\n1 unicorn statue")
    att = Attachment(kind="file", filename="order.txt", mime_type="text/plain",
                     content_b64=base64.b64encode(order_txt.encode()).decode())
    out = svc._try_file_bulk_order("please check the attachment and order", [att], "CUST-1001")
    assert out is not None
    pay = svc._last_checkout
    assert pay and pay.get("ok") is True
    cart = {c["name"].split()[0].lower(): c["qty"] for c in pay["cart"]}
    assert pay["cart"] and len(pay["cart"]) == 4          # 4 matched, unicorn skipped
    # Per-line quantities honored.
    soccer = next(c for c in pay["cart"] if "soccer" in c["name"].lower())
    oreo = next(c for c in pay["cart"] if "oreo" in c["name"].lower())
    assert soccer["qty"] == 2 and oreo["qty"] == 3
    assert "unicorn" in out[0].lower()                     # reported as not found


def test_bulk_order_from_xlsx_uses_file_items_not_default_basket():
    """An uploaded .xlsx (binary) must be parsed by product_name/sku + quantity —
    NOT decoded as text (which silently fell back to the default basket)."""
    import base64
    import io
    import openpyxl
    from backend.app.models.schemas import Attachment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["product_name", "order_quantity", "sku", "category"])
    ws.append(["Cheez-It Original Baked Snack Crackers", 50, "FOOD-CHZ-2005", "Food"])
    ws.append(["Coca-Cola Classic Soda", 120, "FOOD-COC-2004", "Food"])
    ws.append(["LEGO Classic Creative Bricks Box", 5, "TOY-LEG-3002", "Toys"])
    buf = io.BytesIO(); wb.save(buf)
    att = Attachment(kind="file", filename="enterprise_bulk_order.xlsx",
                     mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     content_b64=base64.b64encode(buf.getvalue()).decode())

    svc = AgentService()
    out = svc._try_file_bulk_order("place a bulk order from the attached file", [att], "CUST-1001")
    assert out is not None
    cart = svc._last_checkout
    assert cart and cart.get("ok") is True
    names = " ".join(c["name"].lower() for c in cart["cart"])
    assert "cheez" in names and "coca" in names and "lego" in names   # exactly the file's items
    qty = {c["name"].split()[0].lower(): c["qty"] for c in cart["cart"]}
    assert qty.get("cheez-it") == 50 and qty.get("coca-cola") == 120   # file quantities honored
    # the default basket leaks a clothing dress (a.n.a) — must NOT be here
    assert "a.n.a" not in names and "dress" not in names


def test_place_bulk_order_persists_multi_item_order():
    res = place_bulk_order("CUST-1001")
    assert res["ok"] is True
    assert res["line_count"] >= 2          # multiple items in one order
    assert res["payment"]["status"] == "SUCCESS"
    repo = get_repository()
    placed = next(o for o in repo.list_orders_for_customer("CUST-1001")
                  if o.order_id == res["order_id"])
    assert len(placed.items) == res["line_count"]


def test_place_bulk_order_intent_routes_to_checkout():
    svc = AgentService()
    # Step 1: preview asks to confirm (nothing placed yet).
    prev = svc.run_turn(
        ChatRequest(message="place bulk order", session_id="bulk-intent"),
        customer_id="CUST-1001",
    )
    assert "checkout_agent" in prev.used_tools
    assert prev.checkout and prev.checkout.get("pending") is True
    assert "confirm" in prev.reply.lower()
    # Step 2: confirm → places the bulk order.
    resp = svc.run_turn(
        ChatRequest(message="place bulk order", session_id="bulk-intent", confirm=True),
        customer_id="CUST-1001",
    )
    assert resp.checkout and resp.checkout.get("ok") is True
    assert "bulk order" in resp.reply.lower()


def test_fulfillment_runs_and_inserts_order_placed():
    """Placing an order triggers the order-management pipeline: real inventory
    check + real ORDER_PLACED insert + all 9 stages."""
    from backend.app.tools.order_mgmt_tool import run_fulfillment
    res = place_order("CUST-1001")
    assert res["ok"] is True
    f = res.get("fulfillment", {})
    assert f.get("ok") is True
    assert f.get("tracking_number")
    assert len(f.get("stages", [])) == 9          # full pipeline
    # ORDER_PLACED row exists for this order.
    repo = get_repository()
    rows = repo._conn.execute(
        "SELECT order_id FROM order_placed WHERE order_id=?", (res["order_id"],)
    ).fetchall() if hasattr(repo, "_conn") else [(res["order_id"],)]
    assert any(r[0] == res["order_id"] for r in rows)
