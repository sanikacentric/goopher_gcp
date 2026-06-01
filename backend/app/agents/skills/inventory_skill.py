"""
Inventory Agent Skill (Requirement T4: USE AGENT SKILLS).

An "agent skill" here = a cohesive bundle of (a) an instruction snippet that
teaches the LLM when/how to use the capability, and (b) the callable tools that
implement it. The orchestrator composes skills rather than loose functions, so
capabilities can be added/removed as units.

The tools are plain Python functions (tools/inventory_tool.py) registered
directly with the ADK agent as in-process function tools.
"""
from __future__ import annotations

from ...tools.inventory_tool import check_stock, get_product_details, search_inventory

INSTRUCTION = """
You can answer questions about the store's three departments — women's casual
Clothing, Food/Snacks, and Toys — using the inventory tools:
- Use `search_inventory` for browsing/discovery in any department ("show me
  black midi dresses under $40", "do you have barbecue chips", "show me toys",
  "is the LEGO set in stock"). Pass color/size/max_price filters when mentioned.
- Use `inventory_check_stock` when the shopper asks whether a specific variant
  is available, naming a variant_id or a product+option (color/flavor + size).
- Use `get_product_details` for deep questions about one product (material or
  ingredients, all options/sizes, rating).
Always quote the current sale price and call out low stock (<5 units) or
out-of-stock variants so the shopper can decide quickly.
""".strip()


def get_tools() -> list:
    """Return the skill's tool callables (used directly or wrapped by ADK)."""
    return [search_inventory, check_stock, get_product_details]
