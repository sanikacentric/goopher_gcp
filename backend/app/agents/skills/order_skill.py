"""
Order Management Agent Skill (Requirement T4 + Req 3).

Bundles instruction + tools for both INDIVIDUAL order tracking and HIGH-VOLUME
bulk status. The tools are plain functions (tools/order_tool.py) registered
directly with the ADK agent as in-process function tools.
"""
from __future__ import annotations

from ...tools.order_tool import bulk_order_status, get_order_status, list_customer_orders

INSTRUCTION = """
You help customers manage orders for the store (clothing, food & toys):
- Use `get_order_status` for a single order number (e.g. ORD-50002). Report the
  status, carrier, tracking number, and estimated/actual delivery date.
- Use `order_list_for_customer` to show all orders for the signed-in customer
  (their customer_id is provided in context). Never ask for it.
- Use `order_bulk_status` when the user pastes or requests MANY order numbers at
  once (high-volume management). Summarize counts (found/missing) before details.
Be proactive: if an order is "Shipped", offer the tracking link; if
"Processing", give the estimated delivery.
""".strip()


def get_tools() -> list:
    return [get_order_status, list_customer_orders, bulk_order_status]
