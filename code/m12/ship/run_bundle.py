"""Start an unpacked .mcpb the way a host does: read manifest.json, put the folder into ${__dirname}, run mcp_config.
  python run_bundle.py <unpacked_dir>
Runs it twice: the first start has no .venv yet (uv builds it from uv.lock), the second start reuses it."""
import asyncio, json, sys, time
from pathlib import Path

from mcp import Client, StdioServerParameters


async def start_once(folder: Path):
    cfg = json.loads((folder / "manifest.json").read_text())["server"]["mcp_config"]
    args = [a.replace("${__dirname}", str(folder)) for a in cfg["args"]]
    t0 = time.perf_counter()
    async with Client(StdioServerParameters(command=cfg["command"], args=args)) as c:
        ready = (time.perf_counter() - t0) * 1000
        tools = [t.name for t in (await c.list_tools()).tools]
        r = await c.call_tool("place_order", {"items": [{"drink": "Latte", "size": "Large", "milk": "oat"}],
                                              "handoff": {"kind": "pickup", "name": "Sam"}})
        info = c.server_info
    return {"ready_ms": round(ready), "server": f"{info.name} {info.version}" if info else None, "tools": tools,
            "place_order('Latte','Large')": r.structured_content if not r.is_error else r.content[0].text}


async def main(folder):
    folder = Path(folder).resolve()
    for label in ("cold start (no .venv)", "warm start"):
        print(label, json.dumps(await start_once(folder)))
    print("venv created inside the bundle folder:", (folder / ".venv").is_dir())

asyncio.run(main(sys.argv[1]))
