"""
Order-status tool logic (Requirement 2A-2: order status retrieval) and the
high-volume / bulk path (Requirement 3: individual AND high-volume management).

Registered directly as ADK function tools via the order skill (in-process).
"""
from __future__ import annotations

from ..config import get_settings
from ..db.database import get_repository
from ..observability.telemetry import incr, log_event

_settings = get_settings()


def get_order_status(order_id: str) -> dict:
    """
    Retrieve the status & tracking detail for a single order.

    Args:
        order_id: e.g. "ORD-50002".
    """
    incr("tool_calls_total")
    repo = get_repository()
    order = repo.get_order(order_id)
    log_event("order_status", order_id=order_id, found=order is not None)
    if order is None:
        return {"found": False, "order_id": order_id,
                "message": "Order not found. Double-check the order number."}
    return {"found": True, **order.model_dump()}


def list_customer_orders(customer_id: str) -> dict:
    """List all orders for an authenticated customer (individual management)."""
    incr("tool_calls_total")
    repo = get_repository()
    orders = repo.list_orders_for_customer(customer_id)
    log_event("order_list", customer_id=customer_id, count=len(orders))
    return {
        "count": len(orders),
        "orders": [o.model_dump() for o in orders],
    }


def bulk_order_status(order_ids: list[str]) -> dict:
    """
    High-volume order management (Requirement 3).

    Resolve status for many orders in one call — useful for business shoppers,
    customer-service reps, or batch reconciliation. Capped by
    `settings.bulk_max_orders` to protect the backend.
    """
    incr("tool_calls_total")
    repo = get_repository()
    capped = order_ids[: _settings.bulk_max_orders]
    found, missing = [], []
    for oid in capped:
        order = repo.get_order(oid)
        (found.append(order.model_dump()) if order else missing.append(oid))
    log_event("order_bulk", requested=len(order_ids), found=len(found),
              missing=len(missing), capped=len(order_ids) > len(capped))
    return {
        "requested": len(order_ids),
        "processed": len(capped),
        "found": len(found),
        "orders": found,
        "missing": missing,
        "truncated": len(order_ids) > len(capped),
    }
