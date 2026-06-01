"""
Checkout Agent Skill (Requirement 4: place an order).

Bundles the instruction + tools that let a shopper place an order: add to cart,
run a simulated payment, and persist the order. The tools are plain Python
functions (tools/checkout_tool.py) registered directly with the ADK agent.
"""
from __future__ import annotations

from ...tools.checkout_tool import add_to_cart, place_order, process_payment

INSTRUCTION = """
You handle CHECKOUT — placing an order for the store (clothing & food):
- When the shopper says "place an order", "buy", "checkout", or "order this",
  call `place_order` with the signed-in customer_id (given in context). If they
  named a specific product/variant, pass its variant_id; otherwise leave it empty
  and a popular in-stock item is chosen automatically.
- `place_order` adds to cart, runs the payment, and persists the order in one
  step. Then tell the customer: payment SUCCESSFUL, the new order id, the item,
  the amount charged, and the estimated delivery date.
- `add_to_cart` and `process_payment` are available if you need the steps
  separately. Payment is simulated (always succeeds) — this is a demo.
Be upbeat and concrete; always surface the order id and the total.
""".strip()


def get_tools() -> list:
    return [place_order, add_to_cart, process_payment]
