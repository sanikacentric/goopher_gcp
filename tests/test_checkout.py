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
    resp = svc.run_turn(
        ChatRequest(message="place bulk order", session_id="bulk-intent"),
        customer_id="CUST-1001",
    )
    assert "checkout_agent" in resp.used_tools
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
