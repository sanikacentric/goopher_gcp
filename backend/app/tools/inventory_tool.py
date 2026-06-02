"""
Inventory tool logic (Requirement 2A-1: real-time inventory retrieval).

These are plain, well-tested Python functions registered directly as ADK
function tools (in-process) via the agent skills, and also called by the
deterministic fallback engine. Keeping the logic in plain functions makes it
unit-testable without any agent/LLM.
"""
from __future__ import annotations

from ..db.database import get_repository
from ..observability.telemetry import incr, log_event

# The most recently shown product — lets the agent resolve contextual orders
# ("order it", "order the above item") to what the shopper was just looking at.
# Process-global is fine for this single-user demo; both the ADK worker and the
# deterministic path call these tools, so it's populated either way.
_LAST_VIEWED: dict | None = None


def get_last_viewed() -> dict | None:
    """{'name', 'sku'} of the most recently shown product, or None."""
    return _LAST_VIEWED


def _set_last_viewed(name: str, sku: str) -> None:
    global _LAST_VIEWED
    _LAST_VIEWED = {"name": name, "sku": sku}
    log_event("last_viewed_set", sku=sku)


def search_inventory(query: str = "", color: str = "", size: str = "",
                     max_price: float | None = None) -> dict:
    """
    Search the store catalog (clothing & food).

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
    if products:  # remember the top result for contextual orders ("order it")
        _set_last_viewed(products[0].name, products[0].sku)
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
                "message": "No such variant in the store catalog."}
    return {"found": True, **info}


def get_product_details(sku: str) -> dict:
    """Return the full product record (all variants + stock) for a SKU."""
    incr("tool_calls_total")
    repo = get_repository()
    p = repo.get_product(sku)
    log_event("inventory_product_details", sku=sku, found=p is not None)
    if p is None:
        return {"found": False, "sku": sku}
    _set_last_viewed(p.name, p.sku)   # remember for contextual orders
    return {"found": True, **p.model_dump()}
