"""
Multi-modal Subagent (Requirement 2A-6: text, voice, images, files).

Normalizes any inbound modality into text the orchestrator can reason over, and
records which modality was used so memory/observability stay accurate.

  * text   — passed through.
  * voice  — audio attachment is transcribed (Gemini is natively multimodal;
             here we describe the contract and provide a hook).
  * image  — e.g. a shopper photographs a dress -> we ask Gemini to describe it
             and extract searchable attributes (color, style) to feed inventory.
  * file   — e.g. a CSV/PDF of order numbers -> extract IDs for bulk lookup.

For images/audio we rely on Gemini's multimodal input. To keep the demo
dependency-light and deterministic for tests, the heavy lifting is optional and
guarded; the text path always works.
"""
from __future__ import annotations

import base64
import csv
import io
import re
from typing import Optional

from ..models.schemas import Attachment


def classify_modality(message: str, attachments: list[Attachment]) -> str:
    """Pick the primary modality for this turn (used for memory/telemetry)."""
    if not attachments:
        return "text"
    kinds = {a.kind for a in attachments}
    if "audio" in kinds:
        return "voice"
    if "image" in kinds:
        return "image"
    return "file"


def extract_order_ids_from_text(text: str) -> list[str]:
    """Find order IDs like ORD-50002 anywhere in free text (for bulk requests)."""
    return re.findall(r"ORD-\d{4,}", text or "", flags=re.IGNORECASE)


def extract_order_ids_from_file(att: Attachment) -> list[str]:
    """
    Parse an uploaded CSV/plain-text file of order numbers for high-volume
    management. Accepts a single column or comma-separated values.
    """
    if not att.content_b64:
        return []
    try:
        raw = base64.b64decode(att.content_b64).decode("utf-8", errors="ignore")
    except Exception:
        return []
    ids: list[str] = []
    # Try CSV first, then fall back to regex over the raw text.
    try:
        for row in csv.reader(io.StringIO(raw)):
            for cell in row:
                ids.extend(extract_order_ids_from_text(cell))
    except Exception:
        pass
    if not ids:
        ids = extract_order_ids_from_text(raw)
    # De-dupe while preserving order.
    seen: set[str] = set()
    return [x.upper() for x in ids if not (x.upper() in seen or seen.add(x.upper()))]


def describe_image(att: Attachment, model: str) -> Optional[str]:
    """
    Ask the LLM (OpenAI vision) to describe an uploaded product image and extract
    search terms. Returns a short text description, or None if unavailable.

    `model` is the orchestrator's configured model name; for OpenAI this should
    be a vision-capable model (e.g. gpt-4o-mini). The Gemini implementation is
    kept commented below for future use.
    """
    if not att.content_b64:
        return None

    from ..config import get_settings  # local import to avoid cycles

    settings = get_settings()
    prompt = (
        "Describe this retail product for a catalog search in one sentence: "
        "item type, color, and key style/flavor details."
    )

    # --- OpenAI vision (ACTIVE) ---
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            client = OpenAI(**kwargs)
            data_url = f"data:{att.mime_type};base64,{att.content_b64}"
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                max_tokens=120,
            )
            return (resp.choices[0].message.content or "").strip() or None
        except Exception:
            return None

    # --- GEMINI (COMMENTED OUT — kept for future use) ---
    # try:
    #     import google.generativeai as genai  # lazy import
    #     gmodel = genai.GenerativeModel(model)
    #     image_part = {"mime_type": att.mime_type, "data": base64.b64decode(att.content_b64)}
    #     resp = gmodel.generate_content([prompt, image_part])
    #     return resp.text.strip()
    # except Exception:
    #     return None
    return None


def normalize_to_text(message: str, attachments: list[Attachment], model: str) -> str:
    """
    Fold all modalities into a single text prompt for the orchestrator.

    Images become descriptions; files contribute extracted order IDs; the
    original text is preserved. The result is what the LLM actually reasons over.
    """
    parts: list[str] = []
    if message:
        parts.append(message)

    for att in attachments:
        if att.kind == "image":
            desc = describe_image(att, model)
            if desc:
                parts.append(f"[Image uploaded — looks like: {desc}]")
            else:
                parts.append(f"[Image '{att.filename}' uploaded]")
        elif att.kind == "file":
            ids = extract_order_ids_from_file(att)
            if ids:
                parts.append(f"[File '{att.filename}' contains order IDs: {', '.join(ids)}]")
            else:
                parts.append(f"[File '{att.filename}' uploaded]")
        elif att.kind == "audio":
            # Gemini can transcribe audio; contract documented, hook left open.
            parts.append(f"[Voice message '{att.filename}' received]")

    return "\n".join(parts).strip()
