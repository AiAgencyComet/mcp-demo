"""Fernhill price server with a cache hint on tools/list. Usage: server_ttl.py PORT TTL_MS"""
import sys
from mcp.server import MCPServer
from mcp.server.caching import CacheHint
PORT, TTL = int(sys.argv[1]), int(sys.argv[2])
mcp = MCPServer("fernhill", cache_hints={"tools/list": CacheHint(ttl_ms=TTL, scope="public")} if TTL else None)
@mcp.tool()
def get_price(drink: str) -> str:
    """Return the price of one drink in US dollars."""
    return {"latte": "4.50", "flat white": "4.20", "cold brew": "5.00"}.get(drink.lower(), "not on the menu")
mcp.run(transport="streamable-http", port=PORT)
