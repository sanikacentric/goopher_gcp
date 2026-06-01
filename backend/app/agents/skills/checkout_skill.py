"""
Checkout Agent Skill (Requirement 4: place an order).

Bundles the instruction + tools that let a shopper place an order: add to cart,
run a simulated payment, and persist the order. The tools are plain Python
functions (tools/checkout_tool.py) registered directly with the ADK agent.
"""
from __future__ import annotations

from ...tools.checkout_tool import (
    add_to_cart,
    place_bulk_order,
    place_order,
    process_payment,
    resolve_variant_by_name,
)

INSTRUCTION = """
You handle CHECKOUT — placing orders for the store (clothing, food & toys):
- "place an order" / "buy" / "checkout" / "order this" (a SINGLE item):
  * If the shopper NAMED a product (e.g. "place an order of oreo cookies"),
    FIRST call `resolve_variant_by_name` with that name to get the exact
    variant_id, then call `place_order` with that variant_id. If
    `resolve_variant_by_name` returns ok=false (not found or out of stock),
    DO NOT place any order and DO NOT substitute a different product — just tell
    the shopper the item wasn't available, using its message.
  * Only when NO specific product was named (a bare "place an order") may you
    call `place_order` with an empty variant_id (a popular in-stock item is
    chosen to demonstrate the flow).
- "place bulk order" / "bulk order" / "order multiple" / "buy several" (MANY
  items in one order): call `place_bulk_order` with the customer_id. Pass
  variant_ids if specific products were named; otherwise leave empty and a
  representative multi-item basket is chosen automatically.
- A successful order adds to cart, runs the (simulated, always-successful)
  payment, and persists the order. Then tell the customer: payment SUCCESSFUL,
  the new order id, the item(s), the amount charged, and the estimated delivery.
- `add_to_cart` and `process_payment` are available for the steps separately.
NEVER substitute a different product for one the shopper asked for. Be upbeat
and concrete; always surface the order id and the total.
""".strip()


def get_tools() -> list:
    return [resolve_variant_by_name, place_order, place_bulk_order, add_to_cart, process_payment]
