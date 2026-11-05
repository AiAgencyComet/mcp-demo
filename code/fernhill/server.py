"""The Fernhill MCP server: tools, resources and prompts. Spec 2026-07-28, mcp 2.3.0.
Run:  python server.py            (stdio, for Claude Desktop and Claude Code)
      python server.py http 8200  (Streamable HTTP)"""
import sys
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from mcp.server import MCPServer
from mcp.server.mcpserver import AcceptedElicitation, Elicit, ElicitationResult, Resolve
from mcp.server.mcpserver.exceptions import ToolError
import shop

mcp = MCPServer("fernhill", instructions="Tools for the Fernhill Coffee shop: menu, orders and refunds.")

# ---------- tools: actions that the model can do ----------

class MenuItem(BaseModel):
    drink: str
    price: float = Field(description="Price in US dollars")
    sizes: list[str]

@mcp.tool()
def get_menu() -> list[MenuItem]:
    """Return every item on the Fernhill menu with its price and sizes."""
    return [MenuItem(drink=d, **v) for d, v in shop.MENU.items()]

class Pickup(BaseModel):
    kind: Literal["pickup"]
    name: str = Field(description="Name to call at the counter")

class Delivery(BaseModel):
    kind: Literal["delivery"]
    address: str

class Item(BaseModel):
    drink: str = Field(description="A drink name from get_menu")
    size: str
    milk: Literal["whole", "oat", "none"] = "whole"

class Order(BaseModel):
    order_id: str = Field(description="Give this ID to order_status and refund")
    total: float
    status: str

@mcp.tool()
def place_order(items: list[Item], handoff: Pickup | Delivery) -> Order:
    """Place a new order. Returns an order_id. Use that order_id in later calls."""
    for it in items:
        if it.drink not in shop.MENU:
            raise ToolError(f"'{it.drink}' is not on the menu. Call get_menu to see the menu.")
        if it.size not in shop.MENU[it.drink]["sizes"]:
            raise ToolError(f"'{it.size}' is not a size for {it.drink}. Sizes: {shop.MENU[it.drink]['sizes']}.")
    total = round(sum(shop.MENU[i.drink]["price"] + (0.60 if i.milk == "oat" else 0) for i in items), 2)
    order_id = f"A-{1041 + len(shop.ORDERS)}"
    shop.ORDERS[order_id] = {"items": [i.model_dump() for i in items], "total": total, "status": "making",
                             "handoff": handoff.model_dump()}
    return Order(order_id=order_id, total=total, status="making")

@mcp.tool()
def order_status(order_id: str) -> Order:
    """Return the status of one order."""
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}. Order IDs look like A-1041.")
    o = shop.ORDERS[order_id]
    return Order(order_id=order_id, total=o["total"], status=o["status"])

class Confirm(BaseModel):
    confirm: bool

def ask_person(order_id: str):
    total = shop.ORDERS.get(order_id, {}).get("total", 0)
    return Elicit(f"Refund ${total:.2f} for order {order_id}?", Confirm)

@mcp.tool()
def refund(order_id: str, answer: Annotated[ElicitationResult[Confirm], Resolve(ask_person)]) -> str:
    """Refund one order. The person must confirm first."""
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}.")
    if isinstance(answer, AcceptedElicitation) and answer.data.confirm:
        shop.ORDERS[order_id]["status"] = "refunded"
        return f"Refunded ${shop.ORDERS[order_id]['total']:.2f} for {order_id}."
    return "The person stopped the refund."

# ---------- resources: data that the host or the model can read ----------

@mcp.resource("fernhill://menu", mime_type="application/json")
def menu_resource() -> dict:
    """The full menu."""
    return shop.MENU

@mcp.resource("fernhill://orders/{order_id}", mime_type="application/json")
def order_resource(order_id: str) -> dict:
    """One order, by ID."""
    return shop.ORDERS[order_id]

@mcp.resource("fernhill://policy/refunds", mime_type="text/plain")
def refund_policy() -> str:
    """The refund policy of the shop."""
    return shop.REFUND_POLICY

# ---------- prompts: templates that the person chooses ----------

@mcp.prompt()
def daily_report(day: str) -> str:
    """Write the end-of-day report for one day."""
    return (f"Write the Fernhill end-of-day report for {day}. "
            "Read the orders with order_status. List the total sales, the top drink and any refunds.")

@mcp.prompt()
def complaint_reply(order_id: str, complaint: str) -> str:
    """Write a polite reply to a customer complaint."""
    return (f"A customer complains about order {order_id}: '{complaint}'. "
            "Read fernhill://policy/refunds first. Then write a short, polite reply. Offer a refund only if the policy lets you.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        mcp.run(transport="streamable-http", port=int(sys.argv[2]))
    else:
        mcp.run()
