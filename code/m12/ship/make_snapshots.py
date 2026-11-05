"""Save the tools/list of each release as a JSON snapshot -> data/m12/versioning/tools_<version>.json
Three come from real servers (MCP tools/list). Two are small edits of v1.1.0, to show one rule each."""
import asyncio, copy, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[1] / "fernhill")]
from mcp import Client
import server as v1
from releases import fernhill_v1_1, fernhill_v2_bad

OUT = HERE.parents[2] / "data" / "m12" / "versioning"


async def snapshot(srv):
    async with Client(srv) as c:
        tools = (await c.list_tools()).tools
    return [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools]


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    snaps = {"1.0.0": await snapshot(v1.mcp), "1.1.0": await snapshot(fernhill_v1_1.mcp),
             "2.0.0-rc1": await snapshot(fernhill_v2_bad.mcp)}

    add = copy.deepcopy(snaps["1.1.0"])                      # 1.2.0: optional field + new tool
    po = next(t for t in add if t["name"] == "place_order")
    po["inputSchema"]["properties"]["note"] = {"type": "string", "default": "", "description": "A note for the barista"}
    add.append({"name": "get_stock", "description": "Return how many units of one stock item are left.",
                "inputSchema": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}})
    snaps["1.2.0-additive"] = add

    req = copy.deepcopy(snaps["1.1.0"])                      # "1.2.0": a new REQUIRED field, an enum value removed
    po = next(t for t in req if t["name"] == "place_order")
    po["inputSchema"]["properties"]["pickup_time"] = {"type": "string", "description": "HH:MM"}
    po["inputSchema"]["required"].append("pickup_time")
    po["inputSchema"]["$defs"]["Item"]["properties"]["milk"]["enum"] = ["whole", "oat"]
    snaps["1.2.0-required"] = req

    for v, s in snaps.items():
        (OUT / f"tools_{v}.json").write_text(json.dumps(s, indent=1))
        print(f"tools_{v}.json  {len(s)} tools  {[t['name'] for t in s]}")

asyncio.run(main())
