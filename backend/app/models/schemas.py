"""
Pydantic data models shared across the API, agents, tools, and tests.

Keeping a single source of truth for shapes means the Chrome extension, the
agents, and the database layer all agree on field names and types.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Catalog / inventory
# --------------------------------------------------------------------------- #
class Variant(BaseModel):
    variant_id: str
    color: str
    size: str
    stock: int = Field(ge=0, description="Units available in inventory.")


class Product(BaseModel):
    # "Clothing" or "Food" — lets the agent and storefront group items by aisle.
    # Optional with a default so older/clothing-only data still validates.
    department: str = "Clothing"
    sku: str
    name: str
    brand: str
    category: str
    description: str
    list_price: float
    sale_price: float
    rating: float
    review_count: int
    # For clothing these are colors/sizes; for food they hold flavors/pack sizes.
    colors: list[str]
    sizes: list[str]
    material: str  # for food this carries the key ingredients/notes
    variants: list[Variant]


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
class OrderItem(BaseModel):
    variant_id: str
    name: str
    color: str
    size: str
    qty: int
    unit_price: float


OrderStatus = Literal["Processing", "Shipped", "Delivered", "Cancelled", "Returned"]


class Order(BaseModel):
    order_id: str
    customer_id: str
    status: OrderStatus
    order_date: str
    estimated_delivery: Optional[str] = None
    delivered_date: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    shipping_address: str
    items: list[OrderItem]
    total: float


# --------------------------------------------------------------------------- #
# Customers / auth
# --------------------------------------------------------------------------- #
class Customer(BaseModel):
    customer_id: str
    email: str
    name: str
    loyalty_tier: str = "Standard"
    preferred_language: str = "en"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: Customer


# --------------------------------------------------------------------------- #
# Chat / agent I/O
# --------------------------------------------------------------------------- #
class Attachment(BaseModel):
    """A multi-modal attachment (image/file) sent from the extension."""
    kind: Literal["image", "file", "audio"]
    filename: str
    mime_type: str
    # Base64 content kept small for the demo; production would use signed URLs / GCS.
    content_b64: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = ""
    session_id: str = Field(..., description="Stable per-conversation id for memory.")
    channel: Literal["web", "phone"] = "web"
    language: Optional[str] = Field(
        default=None, description="ISO code; auto-detected when omitted."
    )
    attachments: list[Attachment] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    language: str
    channel: str
    # Surfaced for observability / debugging in the extension dev console.
    used_tools: list[str] = Field(default_factory=list)
    trace_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# High-volume / bulk order management
# --------------------------------------------------------------------------- #
class BulkOrderQuery(BaseModel):
    order_ids: list[str]


class BulkOrderResult(BaseModel):
    requested: int
    found: int
    orders: list[Order]
    missing: list[str]
