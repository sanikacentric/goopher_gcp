"""
Inventory tool logic (Requirement 2A-1: real-time inventory retrieval).

These are plain, well-tested Python functions. They are exposed two ways:
  1. As MCP tools (see mcp/server.py) — the canonical integration per T5.
  2. Imported directly by the ADK agent skills for in-process speed.

Keeping the logic here (not in the MCP wiring) makes it unit-testable without
spinning up a server.
"""
from __future__ import annotations

from ..db.database import get_repository
from ..observability.telemetry import incr, log_event


def search_inventory(query: str = "", color: str = "", size: str = "",
                     max_price: float | None = None) -> dict:
    """
    Search the JCPenney casual-dress catalog.

    Args:
        query: free-text match against name/brand/description/material.
        color: optional exact color filter (case-insensitive).
        size:  optional exact size filter (XS..XXL).
        max_price: optional ceiling on the current sale price.

    Returns a dict with a list of matching products and per-variant live stock.
    """
    incr("tool_calls_total")
    repo = get_repository()
    products = repo.search_products(query=query, color=color, size=size, max_price=max_price)
    log_event("inventory_search", query=query, color=color, size=size,
              max_price=max_price, results=len(products))
    return {
        "count": len(products),
        "products": [
            {
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "sale_price": p.sale_price,
                "list_price": p.list_price,
                "rating": p.rating,
                "colors": p.colors,
                "sizes": p.sizes,
                "in_stock_variants": [
                    {"variant_id": v.variant_id, "color": v.color, "size": v.size, "stock": v.stock}
                    for v in p.variants if v.stock > 0
                ],
            }
            for p in products
        ],
    }


def check_stock(variant_id: str) -> dict:
    """
    Check real-time stock for a specific product variant.

    Args:
        variant_id: e.g. "JCP-ANA-1001-NVY-M".

    Returns live availability or a not-found marker.
    """
    incr("tool_calls_total")
    repo = get_repository()
    info = repo.check_stock(variant_id)
    log_event("inventory_check_stock", variant_id=variant_id, found=info is not None)
    if info is None:
        return {"found": False, "variant_id": variant_id,
                "message": "No such variant in the casual-dress catalog."}
    return {"found": True, **info}


def get_product_details(sku: str) -> dict:
    """Return the full product record (all variants + stock) for a SKU."""
    incr("tool_calls_total")
    repo = get_repository()
    p = repo.get_product(sku)
    log_event("inventory_product_details", sku=sku, found=p is not None)
    if p is None:
        return {"found": False, "sku": sku}
    return {"found": True, **p.model_dump()}
