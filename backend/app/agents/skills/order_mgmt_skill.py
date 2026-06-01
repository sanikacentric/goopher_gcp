"""
Order Management Agent Skill (Requirement 5).

Bundles the instruction + tool for the post-payment fulfillment pipeline:
validation → inventory check (REAL) → insert ORDER_PLACED (REAL) → confirmation
→ warehouse → shipping → tracking → delivery → invoice. The pipeline streams its
stages to the developer portal for a live stakeholder demo.
"""
from __future__ import annotations

from ...tools.order_mgmt_tool import run_fulfillment

INSTRUCTION = """
You are the ORDER-MANAGEMENT specialist. After an order is placed (payment
successful), call `run_fulfillment` with the order_id and the signed-in
customer_id to run the end-to-end fulfillment pipeline:
validate → check inventory → insert into the ORDER_PLACED table → confirm to the
customer → warehouse pick/pack → ship → track → deliver → invoice.
Report the outcome: inventory status, the tracking number, and that the order
was inserted into ORDER_PLACED and fully processed.
""".strip()


def get_tools() -> list:
    return [run_fulfillment]
