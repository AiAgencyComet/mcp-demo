"""Module 8: the Fernhill order board as an MCP App. Spec 2026-07-28, mcp 2.3.0, MCP Apps 2026-01-26.

Run:  python server.py            (stdio, for Claude Desktop)
      python server.py http 8810  (Streamable HTTP on 127.0.0.1, for the local test host)
"""
import sys
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel
from mcp.server import MCPServer
from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent, ToolAnnotations

import shop_m08 as shop

BOARD_URI = "ui://fernhill/order-board"
BOARD_HTML = (Path(__file__).parent / "board.html").read_text()

apps = Apps()


class OrderRow(BaseModel):
    order_id: str
    name: str
    items: list[str]
    total: float
    status: str
    placed: str


class Board(BaseModel):
    day: str
    orders: list[OrderRow]


class DoneResult(BaseModel):
    order: OrderRow
    open: int
    done: int


def rows() -> list[OrderRow]:
    return [OrderRow(order_id=k, **v) for k, v in shop.ORDERS.items()]


def open_lines() -> str:
    return "\n".join(f"- {r.order_id} {r.name}: {', '.join(r.items)} ({r.status})" for r in rows() if r.status != "done")


# The model calls this tool. The host shows its result in the ui:// resource.
@apps.tool(
    resource_uri=BOARD_URI,
    visibility=["model", "app"],
    title="Order board",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def show_order_board(ctx: Context) -> Annotated[CallToolResult, Board]:
    """Show today's Fernhill orders on an interactive order board. The barista can mark orders done on the board."""
    board = Board(day="Wed 4 Nov", orders=rows())
    n_open = sum(r.status != "done" for r in board.orders)
    # Text for the model and for hosts with no MCP Apps support (graceful degradation).
    lead = "The order board is on screen." if client_supports_apps(ctx) else "Order board (text only)."
    text = f"{lead} {n_open} open orders:\n{open_lines()}"
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structured_content=board.model_dump())


# Only the UI calls this tool. The host does not show it to the model.
@apps.tool(
    resource_uri=BOARD_URI,
    visibility=["app"],
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def mark_order_done(order_id: str) -> Annotated[CallToolResult, DoneResult]:
    """Mark one order as done (the customer has the drink)."""
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}. Order IDs look like A-1043.")
    shop.ORDERS[order_id]["status"] = "done"
    row = OrderRow(order_id=order_id, **shop.ORDERS[order_id])
    n_open = sum(o["status"] != "done" for o in shop.ORDERS.values())
    result = DoneResult(order=row, open=n_open, done=len(shop.ORDERS) - n_open)
    return CallToolResult(
        content=[TextContent(type="text", text=f"{order_id} ({row.name}) is done. {n_open} orders are open.")],
        structured_content=result.model_dump(),
    )


apps.add_html_resource(
    BOARD_URI,
    BOARD_HTML,
    name="order_board",
    title="Fernhill order board",
    description="Interactive board of today's orders, with a 'Mark done' button per order.",
    prefers_border=True,
)

mcp = MCPServer("fernhill-board", instructions="The Fernhill order board for baristas.", extensions=[apps])


# A plain tool for the model only. The UI cannot call it (visibility ["model"]).
@mcp.tool(meta={"ui": {"visibility": ["model"]}}, annotations=ToolAnnotations(readOnlyHint=True))
def order_status(order_id: str) -> str:
    """Return the status of one order."""
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}. Order IDs look like A-1043.")
    return f"{order_id}: {shop.ORDERS[order_id]['status']}"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        mcp.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        mcp.run()
