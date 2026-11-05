"""OLD spec (mcp 1.30.0, 2025-11-25): a refund tool that asks the person to confirm mid-call (elicitation).
Usage: server_old_refund.py PORT stateful|stateless"""
import os, sys
from pydantic import BaseModel
from mcp.server.fastmcp import Context, FastMCP

PORT, MODE = int(sys.argv[1]), sys.argv[2]
mcp = FastMCP("fernhill", port=PORT, log_level="WARNING", stateless_http=(MODE == "stateless"))

class Confirm(BaseModel):
    confirm: bool

@mcp.tool()
async def refund(order_id: str, amount: float, ctx: Context) -> str:
    """Refund an order. The person must confirm first."""
    answer = await ctx.elicit(f"Refund ${amount:.2f} for order {order_id}?", schema=Confirm)
    if answer.action == "accept" and answer.data.confirm:
        return f"Refunded ${amount:.2f} for {order_id} (copy pid {os.getpid()})"
    return f"Refund stopped by the person (copy pid {os.getpid()})"

mcp.run(transport="streamable-http")
