"""Unit tests for the order MCP tool logic (Req 2A-2, Req 3 bulk)."""
from backend.app.mcp.order_tool import (
    bulk_order_status,
    get_order_status,
    list_customer_orders,
)


def test_get_single_order():
    res = get_order_status("ORD-50002")
    assert res["found"] is True
    assert res["status"] == "Shipped"
    assert res["tracking_number"]


def test_get_order_not_found():
    res = get_order_status("ORD-99999")
    assert res["found"] is False


def test_list_customer_orders():
    res = list_customer_orders("CUST-1001")
    assert res["count"] == 3
    statuses = {o["status"] for o in res["orders"]}
    assert {"Delivered", "Shipped", "Processing"} <= statuses


def test_bulk_status_mixed():
    res = bulk_order_status(["ORD-50001", "ORD-50002", "ORD-DOESNOTEXIST"])
    assert res["requested"] == 3
    assert res["found"] == 2
    assert res["missing"] == ["ORD-DOESNOTEXIST"]


def test_bulk_status_high_volume_cap():
    # Way more than the cap -> processed should be capped, truncated flagged.
    many = [f"ORD-{i}" for i in range(10_000)]
    res = bulk_order_status(many)
    assert res["truncated"] is True
    assert res["processed"] <= res["requested"]
