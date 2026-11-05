"""A remote (HTTP) Fernhill tool that takes a long time. Usage: slow_server.py PORT"""
import sys, time
from mcp.server import MCPServer
mcp = MCPServer("fernhill")
@mcp.tool()
def export_sales_report(seconds: int) -> str:
    """Build the Fernhill sales report. It takes `seconds` seconds."""
    time.sleep(seconds)
    return f"Sales report ready after {seconds} s: 412 orders, $2,873.40."
mcp.run(transport="streamable-http", port=int(sys.argv[1]), json_response=True)
