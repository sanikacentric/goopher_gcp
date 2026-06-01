"""
Vision Subagent — Gemini Vision "see it, shop it" (NEW, self-contained).

A dedicated multi-modal subagent that is SEPARATE from the existing modality
pipeline (`modality_agent.py` is intentionally left untouched). The customer
points their camera at a real-world TOY or FOOD item and either:
  * asks "what's the price of this?" → we recognize it and answer, or
  * says "place an order"            → we recognize it and order it.

Flow (kept deliberately simple and grounded):
  1. RECOGNIZE — Gemini Vision (`gemini-2.5-flash`, natively multimodal) names
     the product in the photo. OpenAI vision is a graceful fallback so the demo
     never hard-fails when Gemini isn't configured.
  2. RESOLVE   — map that free-text name to a real catalog product
     (`resolve_variant_by_name`). If we don't carry it, we say so — never
     substitute a different item.
  3. ACT       — classify the customer's intent:
       - ORDER → delegate to the SAME deterministic transactional gate the chat
         path uses (`AgentService._try_checkout`), so the cart + staged receipt +
         `ORDER_PLACED` write are identical to a typed order.
       - PRICE/INFO → answer with the product's real price + availability.

This is invoked by the `POST /vision` endpoint, not `/chat`, so it adds the
capability without modifying any existing request flow.
"""
from __future__ import annotations

import base64
import re
from typing import Optional

from ..config import get_settings
from ..observability.telemetry import incr, log_event


# --------------------------------------------------------------------------- #
# 1. Recognition (Gemini Vision primary, OpenAI vision fallback)
# --------------------------------------------------------------------------- #
_RECOGNIZE_PROMPT = (
    "You are a product-recognition model for a store that sells CLOTHING, FOOD, "
    "and TOYS. Identify the SINGLE main item held up in this photo. Respond with "
    "ONLY its short, common product name (2-5 words) — no sentence, no "
    "punctuation. Examples: 'basketball', 'Oreo cookies', 'LEGO bricks', "
    "'potato chips', 'NERF blaster', 'Play-Doh', 'toy car', 'soda can', "
    "'midi dress'. If it is clearly a toy or a food item, name that item."
)


def _clean_label(text: str) -> str:
    """Reduce the model's answer to a tidy search phrase (first line, no quotes)."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    line = line.strip().strip("\"'`.").strip()
    # Drop a leading "It's a / This is a" if the model added one anyway.
    line = re.sub(r"^(it'?s|this is|that'?s|a|an|the)\s+", "", line, flags=re.IGNORECASE).strip()
    return line[:60]


def _gemini_vision_label(image_b64: str, mime_type: str, settings) -> str:
    """
    Recognize the product with Gemini Vision via the unified `google.genai` SDK,
    which supports BOTH backends:
      * Vertex AI (cloud) — authenticated by the Cloud Run service account
        (USE_VERTEXAI=true, no API key needed). This is what production uses.
      * AI Studio (local) — when GOOGLE_API_KEY is set.
    Returns "" if no usable backend or the call fails.
    """
    from google import genai
    from google.genai import types

    if settings.use_vertexai:
        client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.vertex_location,
        )
    elif settings.google_api_key:
        client = genai.Client(api_key=settings.google_api_key)
    else:
        return ""  # no Gemini credentials available

    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type=mime_type),
            _RECOGNIZE_PROMPT,
        ],
        config=types.GenerateContentConfig(max_output_tokens=64, temperature=0.0),
    )
    return _clean_label(getattr(resp, "text", "") or "")


def _recognize(image_b64: str, mime_type: str) -> tuple[str, str]:
    """Return (product_label, engine). Empty label means recognition failed."""
    settings = get_settings()

    # --- GEMINI VISION (primary) — unified SDK, Vertex AI or AI Studio ---
    if settings.use_vertexai or settings.google_api_key:
        try:
            label = _gemini_vision_label(image_b64, mime_type, settings)
            if label:
                log_event("vision_recognized", engine="gemini", label=label)
                return label, "gemini-vision"
            log_event("vision_gemini_empty")
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            log_event("vision_gemini_failed", reason=str(exc))

    # --- OpenAI vision (fallback so the demo always works) ---
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            client = OpenAI(**kwargs)
            data_url = f"data:{mime_type};base64,{image_b64}"
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _RECOGNIZE_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                max_tokens=64,
            )
            label = _clean_label(resp.choices[0].message.content or "")
            if label:
                log_event("vision_recognized", engine="openai", label=label)
                return label, "openai-vision"
        except Exception as exc:  # noqa: BLE001
            log_event("vision_openai_failed", reason=str(exc))

    return "", "none"


# --------------------------------------------------------------------------- #
# 2. Intent
# --------------------------------------------------------------------------- #
_ORDER_WORDS = (
    "order", "buy", "purchase", "checkout", "check out", "add to cart",
    "get me", "i want", "i'll take", "ill take", "place an order", "grab",
)


def _wants_order(question: str) -> bool:
    q = (question or "").lower()
    return any(w in q for w in _ORDER_WORDS)


# --------------------------------------------------------------------------- #
# 3. Orchestration entrypoint
# --------------------------------------------------------------------------- #
def handle_vision(question: str, image_b64: str, mime_type: str, customer_id: str,
                  session_id: str, channel: str = "web", language: str = "en") -> dict:
    """
    Recognize the item in `image_b64` and act on `question`.

    Returns a dict shaped for `ChatResponse`:
      {reply, checkout, used_tools, recognized}
    """
    incr("tool_calls_total")
    from ..tools.checkout_tool import resolve_variant_by_name
    from ..tools.inventory_tool import get_product_details
    from ..observability.flow_recorder import TurnTrace
    from .orchestrator import get_agent_service

    ft = TurnTrace(kind="vision")
    ft.record.session_id = session_id
    ft.record.customer_id = customer_id
    ft.record.channel = channel
    ft.record.language = language
    ft.record.user_message = (question or "").strip() or "(camera) identify this item"
    used_tools = ["vision_agent"]

    # 1) Recognize
    label, engine = _recognize(image_b64, mime_type)
    ft.step("vision", "gemini_vision: recognize",
            f"identified: {label or 'unknown'}", engine=engine)

    if not label:
        reply = ("I couldn't make out the item in the photo. Try again with the "
                 "item centered and well-lit, or just type the product name.")
        ft.record.reply = reply
        ft.record.used_tools = used_tools
        ft.commit()
        return {"reply": reply, "checkout": None, "used_tools": used_tools,
                "recognized": None}

    # 2) Resolve to a real catalog product (never substitute)
    res = resolve_variant_by_name(label)
    if not res.get("ok"):
        reply = (f'I can see it looks like **{label}**, but we don\'t carry that '
                 f'in the store, so I can\'t price or order it.')
        ft.step("vision", "resolve_catalog", "no catalog match", label=label)
        ft.record.reply = reply
        ft.record.used_tools = used_tools
        ft.commit()
        return {"reply": reply, "checkout": None, "used_tools": used_tools,
                "recognized": {"label": label, "engine": engine, "matched": False}}

    sku, product_name = res["sku"], res["product"]
    ft.step("vision", "resolve_catalog", f"matched {product_name} ({sku})", label=label)
    recognized = {"label": label, "engine": engine, "matched": True,
                  "sku": sku, "product": product_name}

    svc = get_agent_service()

    # 3a) ORDER intent → delegate to the SAME deterministic transactional gate.
    if _wants_order(question):
        # Passing the SKU routes through _try_checkout's SKU resolution, so the
        # cart + staged receipt + ORDER_PLACED write are identical to a typed
        # order. (Vision recognized the item; the gate executes the purchase.)
        gate = svc._try_checkout(f"place an order of {sku}", customer_id)
        if gate is not None:
            reply, _ = gate
            checkout = svc._last_checkout
            used_tools.append("checkout_agent")
            ft.step("vision", "action: place_order",
                    f"ordered {product_name} (via transactional gate)")
            # Lead with what we saw so the customer trusts the recognition.
            reply = f"📷 I recognized **{product_name}**.\n\n{reply}"
            ft.record.reply = reply
            ft.record.used_tools = used_tools
            ft.commit()
            return {"reply": reply, "checkout": checkout, "used_tools": used_tools,
                    "recognized": recognized}

    # 3b) PRICE / INFO intent → answer from the catalog.
    details = get_product_details(sku)
    reply = _format_price_answer(label, details)
    ft.step("vision", "action: price_lookup", product_name)
    ft.record.reply = reply
    ft.record.used_tools = used_tools
    ft.commit()
    return {"reply": reply, "checkout": None, "used_tools": used_tools,
            "recognized": recognized}


def _format_price_answer(label: str, details: dict) -> str:
    """Build a concise price + availability answer from a product record."""
    if not details.get("found"):
        return f'I recognized "{label}" but couldn\'t load its details right now.'
    name = details.get("name", label)
    brand = details.get("brand", "")
    sale = details.get("sale_price")
    listp = details.get("list_price")
    stock = sum(v.get("stock", 0) for v in details.get("variants", []))
    avail = (f"{stock} in stock" if stock else "currently out of stock")
    price = f"${sale:.2f}" if isinstance(sale, (int, float)) else "—"
    was = (f" (was ${listp:.2f})" if isinstance(listp, (int, float)) and listp and listp != sale
           else "")
    brand_txt = f" by {brand}" if brand else ""
    return (f"📷 That looks like the **{name}**{brand_txt}.\n"
            f"Price: **{price}**{was} · {avail}.\n"
            f'Say "place an order" and I\'ll buy it for you.')
