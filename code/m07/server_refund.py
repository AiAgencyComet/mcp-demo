"""Fernhill refund tool that asks the person to confirm before it pays (2026-07-28 multi round-trip).
Usage: server_refund.py PORT ephemeral|shared"""
import os, sys
from typing import Annotated
from pydantic import BaseModel
from mcp.server import MCPServer
from mcp.server.mcpserver import AcceptedElicitation, Elicit, ElicitationResult, Resolve
from mcp.server.request_state import RequestStateSecurity

PORT, MODE = int(sys.argv[1]), sys.argv[2]
security = RequestStateSecurity(keys=[os.environ["FERNHILL_STATE_KEY"]]) if MODE == "shared" else None
mcp = MCPServer("fernhill", request_state_security=security)

class Confirm(BaseModel):
    confirm: bool

def ask_person(order_id: str, amount: float):
    return Elicit(f"Refund ${amount:.2f} for order {order_id}?", Confirm)

@mcp.tool()
def refund(order_id: str, amount: float,
           answer: Annotated[ElicitationResult[Confirm], Resolve(ask_person)]) -> str:
    """Refund an order. The person must confirm first."""
    if isinstance(answer, AcceptedElicitation) and answer.data.confirm:
        return f"Refunded ${amount:.2f} for {order_id} (copy pid {os.getpid()})"
    return f"Refund stopped by the person (copy pid {os.getpid()})"

mcp.run(transport="streamable-http", port=PORT)
