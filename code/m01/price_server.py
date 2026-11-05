"""The same get_price function as an MCP server. Usage: price_server.py PORT"""
import sys
from mcp.server import MCPServer
from price import get_price as _get_price

mcp = MCPServer("fernhill")

@mcp.tool()
def get_price(drink: str) -> str:
    """Return the price of one drink in US dollars."""
    return _get_price(drink)

mcp.run(transport="streamable-http", port=int(sys.argv[1]))
