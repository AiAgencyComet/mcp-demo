"""Fernhill server on the NEW spec (mcp 2.3.0, protocol 2026-07-28). Usage: server_new.py PORT"""
import os, sys
from mcp.server import MCPServer

mcp = MCPServer("fernhill")
MENU = {"latte": 4.50, "flat white": 4.20, "cold brew": 5.00}

@mcp.tool()
def get_price(drink: str) -> str:
    """Return the price of one drink in US dollars."""
    return f"{MENU[drink.lower()]:.2f} (answered by server pid {os.getpid()})"

mcp.run(transport="streamable-http", port=int(sys.argv[1]))
