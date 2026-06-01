"""Tests for the checkout flow (Req 4: place an order)."""
from backend.app.agents.orchestrator import AgentService
from backend.app.db.database import get_repository
from backend.app.models.schemas import ChatRequest
from backend.app.tools.checkout_tool import (
    add_to_cart,
    place_bulk_order,
    place_order,
    process_payment,
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
