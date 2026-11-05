"""Fernhill v2.0.0-rc1: a "clean-up" refactor PR. Same shop logic as code/fernhill/server.py, but:
  - tools renamed to internal codes:  get_menu -> mn_list, place_order -> po_create,
                                      order_status -> po_get, refund -> po_refund
  - every description is now "Tool."  (docstrings and Field descriptions removed)
  - top-level parameters renamed p1, p2
The code works. Its own unit tests pass (tests/test_v2_bad.py). Only the model's view of the tools changed."""
from typing import Annotated, Literal
from pydantic import BaseModel
from mcp.server import MCPServer
from mcp.server.mcpserver import AcceptedElicitation, Elicit, ElicitationResult, Resolve
from mcp.server.mcpserver.exceptions import ToolError
import shop

mcp = MCPServer("fernhill", instructions="Tools for the Fernhill Coffee shop: menu, orders and refunds.")

class MenuItem(BaseModel):
    drink: str
    price: float
    sizes: list[str]

@mcp.tool(description="Tool.")
def mn_list() -> list[MenuItem]:
    return [MenuItem(drink=d, **v) for d, v in shop.MENU.items()]

class Pickup(BaseModel):
    kind: Literal["pickup"]
    name: str

class Delivery(BaseModel):
    kind: Literal["delivery"]
    address: str

class Item(BaseModel):
    drink: str
    size: str
    milk: Literal["whole", "oat", "none"] = "whole"

class Order(BaseModel):
    order_id: str
    total: float
    status: str

@mcp.tool(description="Tool.")
def po_create(p1: list[Item], p2: Pickup | Delivery) -> Order:
    for it in p1:
        if it.drink not in shop.MENU:
            raise ToolError(f"'{it.drink}' is not on the menu. Call mn_list to see the menu.")
        if it.size not in shop.MENU[it.drink]["sizes"]:
            raise ToolError(f"'{it.size}' is not a size for {it.drink}. Sizes: {shop.MENU[it.drink]['sizes']}.")
    total = round(sum(shop.MENU[i.drink]["price"] + (0.60 if i.milk == "oat" else 0) for i in p1), 2)
    order_id = f"A-{1041 + len(shop.ORDERS)}"
    shop.ORDERS[order_id] = {"items": [i.model_dump() for i in p1], "total": total, "status": "making",
                             "handoff": p2.model_dump()}
    return Order(order_id=order_id, total=total, status="making")

@mcp.tool(description="Tool.")
def po_get(p1: str) -> Order:
    if p1 not in shop.ORDERS:
        raise ToolError(f"No order {p1}. Order IDs look like A-1041.")
    o = shop.ORDERS[p1]
    return Order(order_id=p1, total=o["total"], status=o["status"])

class Confirm(BaseModel):
    confirm: bool

def ask_person(p1: str):
    total = shop.ORDERS.get(p1, {}).get("total", 0)
    return Elicit(f"Refund ${total:.2f} for order {p1}?", Confirm)

@mcp.tool(description="Tool.")
def po_refund(p1: str, answer: Annotated[ElicitationResult[Confirm], Resolve(ask_person)]) -> str:
    if p1 not in shop.ORDERS:
        raise ToolError(f"No order {p1}.")
    if isinstance(answer, AcceptedElicitation) and answer.data.confirm:
        shop.ORDERS[p1]["status"] = "refunded"
        return f"Refunded ${shop.ORDERS[p1]['total']:.2f} for {p1}."
    return "The person stopped the refund."

# resources and prompts are unchanged in this PR
@mcp.resource("fernhill://menu", mime_type="application/json")
def menu_resource() -> dict:
    """The full menu."""
    return shop.MENU

@mcp.resource("fernhill://policy/refunds", mime_type="text/plain")
def refund_policy() -> str:
    """The refund policy of the shop."""
    return shop.REFUND_POLICY

# How the eval maps its labels (written against v1 names) to this release. The model never sees this.
LABELS = {"get_menu": "mn_list", "place_order": "po_create", "order_status": "po_get", "refund": "po_refund"}
ARGS = {"po_create": {"p1": "items", "p2": "handoff"}, "po_get": {"p1": "order_id"}, "po_refund": {"p1": "order_id"}}

if __name__ == "__main__":
    mcp.run()
