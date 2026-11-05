"""Start server.py over stdio (the way Claude Desktop starts it) and list its tools and the UI resource."""
import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client import advertise

HERE = Path(__file__).resolve().parent


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "server.py")])
    ui = advertise("io.modelcontextprotocol/ui", {"mimeTypes": ["text/html;profile=mcp-app"]})
    async with Client(params, extensions=[ui]) as c:
        print("stdio protocol version:", c.protocol_version)
        for t in (await c.list_tools()).tools:
            print(" tool", t.name, (t.meta or {}).get("ui"))
        r = await c.read_resource("ui://fernhill/order-board")
        print(" resources/read ->", r.contents[0].mime_type, len(r.contents[0].text), "characters")


asyncio.run(main())
