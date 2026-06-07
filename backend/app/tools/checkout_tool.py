"""
Checkout tool logic (Requirement 4: place an order).

A self-contained "add to cart → dummy payment → order placed" flow. When the
shopper says "place an order", the checkout_agent calls these functions to:
  1. build a cart (from an explicit variant_id, or sensibly default to a popular
     in-stock item so a bare "place an order" still demonstrates the flow),
  2. run a SIMULATED payment (always succeeds — this is a demo, no real gateway),
  3. persist a new order to the catalog and return a confirmation.

Registered as in-process ADK function tools via the checkout skill. The payment
is intentionally fake; swapping in a real PSP (Stripe, etc.) would only touch
`process_payment` without changing the agent contract.
"""
from __future__ import annotations

from ..db.database import get_repository
from ..observability.telemetry import incr, log_event


def _next_order_id() -> str:
    """
    Generate the next ORD-##### id. We probe upward from the seeded range until
    we find a free slot — bounded and simple, fine for a demo catalog.
    """
    repo = get_repository()
    n = 50006
    while n < 50100:  # small bound; demo only
        if repo.get_order(f"ORD-{n}") is None:
            return f"ORD-{n}"
        n += 1
    return f"ORD-{n}"


def resolve_variant_by_name(query: str) -> dict:
    """
    Resolve a free-text product name (e.g. "oreo cookies") to a concrete in-stock
    variant, so a shopper can order by name without knowing the SKU.

    IMPORTANT: this NEVER substitutes a different product. If the named product
    isn't in the catalog, or every variant is out of stock, it returns an error
    (ok=False) and the caller must NOT place an order for something else.

    Returns:
        {"ok": True, "variant_id": ..., "product": ..., "sku": ...} on a hit, or
        {"ok": False, "not_found"|"out_of_stock": True, "message": ...} otherwise.
    """
    incr("tool_calls_total")
    repo = get_repository()
    query = (query or "").strip()
    if not query:
        return {"ok": False, "not_found": True,
                "message": "No product name was given, so no order was placed."}

    products = repo.search_products(query=query)
    log_event("checkout_resolve_name", query=query, results=len(products))
    if not products:
        return {"ok": False, "not_found": True,
                "message": (f'Sorry, we couldn\'t find "{query}" in the catalog, '
                            f'so no order was placed and nothing was substituted. '
                            f'Please check the product name and try again.')}

    # Best match first (search_products ranks by relevance). Pick the first
    # in-stock variant of the best-matching product.
    for p in products:
        for v in p.variants:
            if v.stock > 0:
                return {"ok": True, "variant_id": v.variant_id,
                        "product": p.name, "sku": p.sku}

    # The product exists but is entirely out of stock — do NOT substitute.
    name = products[0].name
    return {"ok": False, "out_of_stock": True,
            "message": (f'"{name}" is currently out of stock, so no order was '
                        f'placed. We did not substitute another item.')}


def add_to_cart(variant_id: str = "", qty: int = 1) -> dict:
    """
    Add a product variant to the cart.

    Args:
        variant_id: e.g. "JCP-ANA-1001-NVY-S". If empty, a popular in-stock item
                    is chosen automatically so a bare "place an order" still works.
        qty: quantity (default 1).
    """
    incr("tool_calls_total")
    repo = get_repository()

    # Resolve the variant (or pick a default in-stock one).
    chosen = None
    if variant_id:
        info = repo.check_stock(variant_id)
        if info and info.get("in_stock"):
            chosen = info
    if chosen is None:
        # Default: first in-stock variant in the catalog.
        for p in repo.list_products():
            for v in p.variants:
                if v.stock > 0:
                    chosen = repo.check_stock(v.variant_id)
                    break
            if chosen:
                break

    if chosen is None:
        return {"ok": False, "message": "No in-stock items available to add."}

    qty = max(1, int(qty))
    line_total = round(chosen["sale_price"] * qty, 2)
    log_event("cart_add", variant_id=chosen["variant_id"], qty=qty)
    return {
        "ok": True,
        "cart": {
            "variant_id": chosen["variant_id"],
            "name": chosen["product"],
            "color": chosen["color"],
            "size": chosen["size"],
            "unit_price": chosen["sale_price"],
            "qty": qty,
            "line_total": line_total,
        },
        "subtotal": line_total,
    }


def process_payment(amount: float, method: str = "card") -> dict:
    """
    Simulate a payment. ALWAYS succeeds (demo only — no real payment gateway).

    Args:
        amount: total to charge.
        method: payment method label (card/upi/wallet).
    """
    incr("tool_calls_total")
    # A fake but realistic-looking transaction id.
    txn = f"PAY-{abs(hash((round(amount, 2), method))) % 10_000_000:07d}"
    log_event("payment_processed", amount=round(amount, 2), method=method, txn=txn)
    return {
        "ok": True,
        "status": "SUCCESS",
        "transaction_id": txn,
        "amount": round(amount, 2),
        "method": method,
        "message": f"Payment of ${amount:.2f} via {method} was successful.",
    }


def place_order(customer_id: str, variant_id: str = "", qty: int = 1) -> dict:
    """
    Full checkout: add to cart -> simulate payment -> persist the order.

    Args:
        customer_id: the signed-in customer (provided in context).
        variant_id: optional specific variant; defaults to a popular in-stock item.
        qty: quantity (default 1).

    Returns a confirmation with the new order id and the (simulated) payment.
    """
    incr("tool_calls_total")
    from ..models.schemas import Order, OrderItem  # local import to avoid cycles

    cart = add_to_cart(variant_id=variant_id, qty=qty)
    if not cart.get("ok"):
        return cart

    line = cart["cart"]
    total = cart["subtotal"]
    payment = process_payment(total, method="card")

    repo = get_repository()
    order_id = _next_order_id()
    order = Order(
        order_id=order_id,
        customer_id=customer_id,
        status="Processing",
        order_date="2026-06-01",
        estimated_delivery="2026-06-08",
        delivered_date=None,
        tracking_number=None,
        carrier=None,
        shipping_address="123 Demo St, Plano, TX 75024",
        items=[OrderItem(
            variant_id=line["variant_id"], name=line["name"],
            color=line["color"], size=line["size"],
            qty=line["qty"], unit_price=line["unit_price"],
        )],
        total=total,
    )
    repo.save_order(order)
    log_event("order_placed", order_id=order_id, customer_id=customer_id, total=total)

    # Payment succeeded -> hand off to the order-management / fulfillment pipeline
    # (inventory check -> insert ORDER_PLACED -> confirmation -> ... -> invoice),
    # which streams its stages live to the dev portal.
    fulfillment = _run_fulfillment_safe(order_id, customer_id)

    data = {
        "ok": True,
        "order_id": order_id,
        "status": "Processing",
        "item": f'{line["name"]} ({line["color"]}, {line["size"]}) x{line["qty"]}',
        # Structured cart so the extension can show a proper cart with the order.
        "cart": [{
            "name": line["name"], "color": line["color"], "size": line["size"],
            "qty": line["qty"], "unit_price": line["unit_price"],
            "line_total": line["line_total"],
        }],
        "subtotal": total,
        "total": total,
        "payment": payment,
        "fulfillment": fulfillment,
        "estimated_delivery": "2026-06-08",
        "message": (f"Payment successful — order {order_id} placed! "
                    f"${total:.2f} charged. Estimated delivery 2026-06-08."),
    }
    data["email"] = _notify_order_email(data)   # best-effort confirmation email
    return data


def _run_fulfillment_safe(order_id: str, customer_id: str) -> dict:
    """Run the order-management pipeline; never let it break checkout."""
    try:
        from .order_mgmt_tool import run_fulfillment
        return run_fulfillment(order_id, customer_id)
    except Exception as exc:  # pragma: no cover - defensive
        log_event("fulfillment_failed", order_id=order_id, reason=str(exc))
        return {"ok": False, "message": f"fulfillment error: {exc}"}


def place_bulk_order(customer_id: str, variant_ids: list[str] | None = None,
                     qty_each: int = 1, quantities: list[int] | None = None) -> dict:
    """
    High-volume checkout: place ONE order containing MULTIPLE line items.

    Args:
        customer_id: the signed-in customer (provided in context).
        variant_ids: specific variants to buy. If empty, a basket of several
                     popular in-stock items (one per product) is chosen so a bare
                     "place bulk order" still demonstrates the flow.
        qty_each: quantity applied to every line when `quantities` is not given.
        quantities: optional PER-LINE quantities, parallel to `variant_ids`
                    (used by the "order from an uploaded file" flow).

    Returns a confirmation listing all line items, the combined total, the
    (simulated) payment, and the new order id.
    """
    incr("tool_calls_total")
    from ..models.schemas import Order, OrderItem  # local import to avoid cycles

    repo = get_repository()

    # Resolve the requested variants, or build a default multi-item basket.
    # Keep each resolved variant paired with its requested quantity.
    resolved: list[dict] = []
    qtys: list[int] = []
    if variant_ids:
        for i, vid in enumerate(variant_ids):
            info = repo.check_stock(vid)
            if info and info.get("in_stock"):
                resolved.append(info)
                q = quantities[i] if quantities and i < len(quantities) else qty_each
                qtys.append(max(1, int(q)))
    if not resolved:
        # Default basket: one in-stock variant from each of the first few products.
        for p in repo.list_products():
            for v in p.variants:
                if v.stock > 0:
                    resolved.append(repo.check_stock(v.variant_id))
                    qtys.append(max(1, int(qty_each)))
                    break
            if len(resolved) >= 3:   # a small representative bulk basket
                break

    if not resolved:
        return {"ok": False, "message": "No in-stock items available for a bulk order."}

    items, total = [], 0.0
    for info, q in zip(resolved, qtys):
        line_total = round(info["sale_price"] * q, 2)
        total += line_total
        items.append(OrderItem(
            variant_id=info["variant_id"], name=info["product"],
            color=info["color"], size=info["size"],
            qty=q, unit_price=info["sale_price"],
        ))
    total = round(total, 2)

    payment = process_payment(total, method="card")
    order_id = _next_order_id()
    order = Order(
        order_id=order_id, customer_id=customer_id, status="Processing",
        order_date="2026-06-01", estimated_delivery="2026-06-08",
        delivered_date=None, tracking_number=None, carrier=None,
        shipping_address="123 Demo St, Plano, TX 75024",
        items=items, total=total,
    )
    repo.save_order(order)
    log_event("bulk_order_placed", order_id=order_id, customer_id=customer_id,
              lines=len(items), total=total)

    fulfillment = _run_fulfillment_safe(order_id, customer_id)

    data = {
        "ok": True,
        "order_id": order_id,
        "status": "Processing",
        "items": [f'{it.name} ({it.color}, {it.size}) x{it.qty} '
                  f'@ ${it.unit_price:.2f}' for it in items],
        "cart": [{
            "name": it.name, "color": it.color, "size": it.size,
            "qty": it.qty, "unit_price": it.unit_price,
            "line_total": round(it.unit_price * it.qty, 2),
        } for it in items],
        "subtotal": total,
        "line_count": len(items),
        "total": total,
        "payment": payment,
        "fulfillment": fulfillment,
        "estimated_delivery": "2026-06-08",
        "message": (f"Payment successful — bulk order {order_id} placed with "
                    f"{len(items)} item(s), ${total:.2f} charged."),
    }
    data["email"] = _notify_order_email(data)   # best-effort confirmation email
    return data


def _notify_order_email(order: dict) -> dict:
    """Send the order-confirmation email; best-effort, never raises."""
    try:
        from .email_tool import send_order_email
        return send_order_email(order)
    except Exception as exc:  # noqa: BLE001
        log_event("order_email_failed", reason=str(exc))
        return {"sent": False, "mode": "error", "detail": str(exc)[:120]}
