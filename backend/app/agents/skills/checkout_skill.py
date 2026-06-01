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
)

INSTRUCTION = """
You handle CHECKOUT — placing orders for the store (clothing & food):
- "place an order" / "buy" / "checkout" / "order this" (a SINGLE item):
  call `place_order` with the signed-in customer_id. Pass variant_id if a
  specific product was named; otherwise leave it empty (a popular in-stock item
  is chosen automatically).
- "place bulk order" / "bulk order" / "order multiple" / "buy several" (MANY
  items in one order): call `place_bulk_order` with the customer_id. Pass
  variant_ids if specific products were named; otherwise leave empty and a
  representative multi-item basket is chosen automatically.
- Both add to cart, run the (simulated, always-successful) payment, and persist
  the order. Then tell the customer: payment SUCCESSFUL, the new order id, the
  item(s), the amount charged, and the estimated delivery date.
- `add_to_cart` and `process_payment` are available for the steps separately.
Be upbeat and concrete; always surface the order id and the total.
""".strip()


def get_tools() -> list:
    return [place_order, place_bulk_order, add_to_cart, process_payment]
