"""Fernhill server on the OLD spec (mcp 1.30.0, protocol 2025-11-25, sessions). Usage: server_old.py PORT"""
import os, sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fernhill", port=int(sys.argv[1]), log_level="WARNING")
MENU = {"latte": 4.50, "flat white": 4.20, "cold brew": 5.00}

@mcp.tool()
def get_price(drink: str) -> str:
    """Return the price of one drink in US dollars."""
    return f"{MENU[drink.lower()]:.2f} (answered by server pid {os.getpid()})"

mcp.run(transport="streamable-http")
