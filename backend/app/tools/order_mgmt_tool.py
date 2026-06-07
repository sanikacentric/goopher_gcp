"""
Order-management / fulfillment pipeline (Requirement 5).

After a payment succeeds, this runs the end-to-end fulfillment workflow and
streams each stage to the developer portal (kind="fulfillment") so a business
stakeholder can watch it live in /dev:

  1. Order Validation        (check payment, address, fraud)        [simulated]
  2. Inventory Check         (is the item in stock?)                [REAL]
  3. Insert into ORDER_PLACED table                                 [REAL DB]
  4. Order Confirmation      (email/SMS to the customer)            [simulated]
  5. Warehouse Processing    (pick → pack)                          [simulated]
  6. Shipping & Logistics    (create label, hand to carrier)        [simulated]
  7. Order Tracking          (customer tracks shipment)             [simulated]
  8. Delivery Confirmation   (item delivered)                       [simulated]
  9. Invoice & Payment Reconciliation                               [simulated]

Inventory IS really checked and the order IS really inserted into the
ORDER_PLACED table; the remaining stages are realistic simulated steps for the
demo (no real warehouse/carrier).
"""
from __future__ import annotations

import time

import os

from ..db.database import get_repository
from ..observability.flow_recorder import commit_record, new_pipeline_record
from ..observability.telemetry import incr, log_event

# Small per-stage delay so the live portal visibly advances during a demo.
# Override with FULFILLMENT_STAGE_DELAY=0 (tests/CI set this to stay fast).
_STAGE_DELAY_S = float(os.environ.get("FULFILLMENT_STAGE_DELAY", "0.6"))


def run_fulfillment(order_id: str, customer_id: str,
                    customer_email: str = "demo@goopher.app") -> dict:
    """
    Execute the fulfillment pipeline for a just-placed order. Returns a summary
    dict; also streams each stage to the dev portal as a 'fulfillment' record.
    """
    incr("tool_calls_total")
    repo = get_repository()
    order = repo.get_order(order_id)
    if order is None:
        return {"ok": False, "message": f"Order {order_id} not found."}

    from ..observability.flow_recorder import FlowStep

    rec = new_pipeline_record(order_id, customer_id)
    rec.reply = f"Fulfilling {order_id} for {customer_email}"
    stages_summary: list[dict] = []

    def add(stage_name: str, detail: str, status: str = "ok", ms: float = 0.0, **data):
        rec.steps.append(FlowStep(stage="fulfillment", name=stage_name,
                                  detail=detail, ms=round(ms, 2),
                                  data={"status": status, **data}))
        commit_record(rec)              # publish progress so the portal updates
        stages_summary.append({"stage": stage_name, "status": status, "detail": detail})
        log_event("fulfillment_stage", order_id=order_id, stage=stage_name, status=status)

    # 1) Order Validation — payment, address, fraud (simulated checks).
    _t = time.perf_counter(); time.sleep(_STAGE_DELAY_S)
    add("1. Order Validation",
        "payment OK · address verified · fraud score LOW",
        ms=(time.perf_counter() - _t) * 1000)

    # 2) Inventory Check — REAL: is every line item in stock?
    _t = time.perf_counter()
    all_in_stock, lines = True, []
    for it in order.items:
        info = repo.check_stock(it.variant_id)
        in_stock = bool(info and info.get("in_stock") and info["stock"] >= it.qty)
        all_in_stock = all_in_stock and in_stock
        lines.append(f'{it.name} x{it.qty}: '
                     f'{"in stock" if in_stock else "LOW/OUT"} '
                     f'({info["stock"] if info else 0} avail)')
    add("2. Inventory Check",
        " · ".join(lines) if lines else "no items",
        status="ok" if all_in_stock else "warn",
        ms=(time.perf_counter() - _t) * 1000, in_stock=all_in_stock)

    # 3) Insert into ORDER_PLACED table — REAL DB write.
    _t = time.perf_counter()
    placed = {
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_email": customer_email,
        "status": "PLACED",
        "items": [it.model_dump() for it in order.items],
        "total": order.total,
        "inventory_ok": all_in_stock,
        "placed_at": order.order_date,
        "estimated_delivery": order.estimated_delivery,
    }
    repo.save_order_placed(placed)
    add("3. Insert ORDER_PLACED",
        f"new record written to ORDER_PLACED table (order_id={order_id})",
        ms=(time.perf_counter() - _t) * 1000)

    # 4) Order Confirmation — email/SMS. The real order-confirmation email is sent
    # (best-effort) after checkout to settings.notify_email; SMS stays simulated.
    _t = time.perf_counter(); time.sleep(_STAGE_DELAY_S)
    try:
        from ..config import get_settings
        _to = get_settings().notify_email or customer_email
    except Exception:  # noqa: BLE001
        _to = customer_email
    add("4. Order Confirmation",
        f"confirmation email to {_to} + SMS (simulated)",
        ms=(time.perf_counter() - _t) * 1000)

    # 5) Warehouse Processing — pick & pack (simulated).
    _t = time.perf_counter(); time.sleep(_STAGE_DELAY_S)
    add("5. Warehouse Processing", "picked → packed at DC-Plano-TX",
        ms=(time.perf_counter() - _t) * 1000)

    # 6) Shipping & Logistics — label + carrier handoff (simulated).
    tracking = f"1Z999AA{abs(hash(order_id)) % 10_000_000:07d}"
    _t = time.perf_counter(); time.sleep(_STAGE_DELAY_S)
    add("6. Shipping & Logistics",
        f"label created · carrier UPS · tracking {tracking}",
        ms=(time.perf_counter() - _t) * 1000, tracking=tracking)
    # Reflect shipping on the order record too.
    order.status = "Shipped"
    order.tracking_number = tracking
    order.carrier = "UPS"
    repo.save_order(order)

    # 7) Order Tracking — customer can track (simulated).
    _t = time.perf_counter()
    add("7. Order Tracking",
        f"shipment trackable · {tracking} · ETA {order.estimated_delivery}",
        ms=(time.perf_counter() - _t) * 1000)

    # 8) Delivery Confirmation (simulated).
    _t = time.perf_counter(); time.sleep(_STAGE_DELAY_S)
    add("8. Delivery Confirmation",
        f"delivered · signed for at {order.shipping_address}",
        ms=(time.perf_counter() - _t) * 1000)

    # 9) Invoice & Payment Reconciliation (simulated).
    _t = time.perf_counter()
    add("9. Invoice & Reconciliation",
        f"invoice INV-{order_id[-5:]} issued · payment reconciled · ${order.total:.2f}",
        ms=(time.perf_counter() - _t) * 1000)

    log_event("fulfillment_complete", order_id=order_id, in_stock=all_in_stock,
              total=order.total)
    return {
        "ok": True,
        "order_id": order_id,
        "inventory_ok": all_in_stock,
        "tracking_number": tracking,
        "stages": stages_summary,
        "message": (f"Order {order_id} fully processed: inventory checked, "
                    f"inserted into ORDER_PLACED, confirmed to {customer_email}, "
                    f"shipped (UPS {tracking}), delivered, and invoiced."),
    }
