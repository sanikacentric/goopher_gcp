"""Unit tests for the inventory MCP tool logic (Req 2A-1)."""
from backend.app.mcp.inventory_tool import (
    check_stock,
    get_product_details,
    search_inventory,
)


def test_search_returns_catalog():
    res = search_inventory()
    assert res["count"] >= 10
    assert all("sku" in p for p in res["products"])


def test_search_filters_by_color():
    res = search_inventory(color="Navy")
    assert res["count"] >= 1
    for p in res["products"]:
        assert "Navy" in p["colors"]


def test_search_filters_by_max_price():
    res = search_inventory(max_price=20.0)
    assert all(p["sale_price"] <= 20.0 for p in res["products"])


def test_search_text_query():
    res = search_inventory(query="wrap dress")
    assert res["count"] >= 1
    assert any("Wrap" in p["name"] for p in res["products"])


def test_check_stock_in_stock():
    res = check_stock("JCP-ANA-1001-NVY-S")
    assert res["found"] is True
    assert res["in_stock"] is True
    assert res["stock"] == 14


def test_check_stock_out_of_stock():
    res = check_stock("JCP-ANA-1001-BLK-M")  # seeded with 0 stock
    assert res["found"] is True
    assert res["in_stock"] is False
    assert res["stock"] == 0


def test_check_stock_not_found():
    res = check_stock("JCP-DOES-NOT-EXIST")
    assert res["found"] is False


def test_product_details():
    res = get_product_details("JCP-WOR-1003")
    assert res["found"] is True
    assert res["brand"] == "Worthington"
    assert len(res["variants"]) >= 1
