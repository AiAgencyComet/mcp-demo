"""Connect to the Fernhill server in-process and save what a host sees. -> data/m04/*.json"""
import asyncio, json
from pathlib import Path
from mcp import Client
import server

OUT = Path(__file__).resolve().parents[2] / "data" / "m04"
def dump(o): return json.loads(o.model_dump_json(by_alias=True, exclude_none=True))

async def main():
    async with Client(server.mcp) as c:
        tools = await c.list_tools(); res = await c.list_resources(); tmpl = await c.list_resource_templates()
        prompts = await c.list_prompts()
        (OUT / "tools_list.json").write_text(json.dumps(dump(tools), indent=1))
        (OUT / "resources_list.json").write_text(json.dumps({"resources": dump(res), "templates": dump(tmpl)}, indent=1))
        (OUT / "prompts_list.json").write_text(json.dumps(dump(prompts), indent=1))
        menu = await c.call_tool("get_menu", {})
        order = await c.call_tool("place_order", {"items": [{"drink": "latte", "size": "large", "milk": "oat"}],
                                                   "handoff": {"kind": "pickup", "name": "Sam"}})
        bad = await c.call_tool("place_order", {"items": [{"drink": "mocha", "size": "large"}],
                                                 "handoff": {"kind": "pickup", "name": "Sam"}})
        pol = await c.read_resource("fernhill://policy/refunds")
        pr = await c.get_prompt("complaint_reply", {"order_id": "A-1042", "complaint": "The cold brew was warm."})
        calls = {"get_menu": dump(menu), "place_order": dump(order), "place_order_bad": dump(bad),
                 "read_policy": dump(pol), "get_prompt": dump(pr)}
        (OUT / "calls.json").write_text(json.dumps(calls, indent=1))
        print("tools:", [t.name for t in tools.tools])
        print("resources:", [str(r.uri) for r in res.resources], "templates:", [t.uri_template for t in tmpl.resource_templates])
        print("prompts:", [p.name for p in prompts.prompts])
        print("place_order ->", order.structured_content)
        print("bad order ->", bad.is_error, bad.content[0].text)
        po = next(t for t in tools.tools if t.name == "place_order")
        print("place_order inputSchema keys:", list(po.input_schema.keys()), "| $defs:", list(po.input_schema.get("$defs", {}).keys()))
        print("handoff schema:", json.dumps(po.input_schema["properties"]["handoff"]))

asyncio.run(main())
