"""
MCP server (Requirement T5 / 2A: integrate inventory & order tools over MCP).

Exposes the inventory and order tool logic as Model Context Protocol tools over
stdio. The ADK orchestrator connects to this server via an MCPToolset (see
agents/orchestrator.py), which is the "USE MCP FOR TOOLS" backend integration.

Run standalone:
    python -m backend.app.mcp.server

The server is intentionally thin: it validates/forwards arguments to the pure
functions in inventory_tool.py / order_tool.py so the same logic is shared by
the in-process agent path and any external MCP client (Claude Desktop, etc.).
"""
from __future__ import annotations

import asyncio

from .inventory_tool import check_stock, get_product_details, search_inventory
from .order_tool import bulk_order_status, get_order_status, list_customer_orders


def build_server():
    """Construct the MCP server with all GOOPHER retail tools registered."""
    # Imported here so the rest of the app doesn't hard-depend on `mcp` being
    # installed (e.g. for unit tests that only exercise the tool logic).
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("goopher-retail")

    # --- Inventory tools (2A-1) ---
    @mcp.tool()
    def inventory_search(query: str = "", color: str = "", size: str = "",
                         max_price: float | None = None) -> dict:
        """Search JCPenney casual dresses by text, color, size, and max price."""
        return search_inventory(query=query, color=color, size=size, max_price=max_price)

    @mcp.tool()
    def inventory_check_stock(variant_id: str) -> dict:
        """Check real-time stock for one product variant (e.g. JCP-ANA-1001-NVY-M)."""
        return check_stock(variant_id)

    @mcp.tool()
    def inventory_product_details(sku: str) -> dict:
        """Get full product detail incl. all variants and stock for a SKU."""
        return get_product_details(sku)

    # --- Order tools (2A-2, Req 3) ---
    @mcp.tool()
    def order_status(order_id: str) -> dict:
        """Get status & tracking for a single order (e.g. ORD-50002)."""
        return get_order_status(order_id)

    @mcp.tool()
    def order_list_for_customer(customer_id: str) -> dict:
        """List all orders for an authenticated customer."""
        return list_customer_orders(customer_id)

    @mcp.tool()
    def order_bulk_status(order_ids: list[str]) -> dict:
        """High-volume: resolve status for many order IDs in a single call."""
        return bulk_order_status(order_ids)

    return mcp


def main() -> None:
    server = build_server()
    # FastMCP.run() handles the stdio transport event loop.
    server.run()


if __name__ == "__main__":
    main()
