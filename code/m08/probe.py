"""Probe the module 8 server in process: tools/list, resources/list, resources/read, and the
graceful-degradation branch (a client with and without the MCP Apps extension).
Writes raw results to data/m08/ and prints a transcript."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client import advertise

sys.path.insert(0, str(Path(__file__).parent))
import server  # noqa: E402
import shop_m08  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "m08"
OUT.mkdir(parents=True, exist_ok=True)
UI_EXT = advertise("io.modelcontextprotocol/ui", {"mimeTypes": ["text/html;profile=mcp-app"]})


def dump(obj):
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True)


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


async def main():
    async with Client(server.mcp, extensions=[UI_EXT]) as c:
        print("protocol version:", c.protocol_version)
        caps = dump(c.server_capabilities)
        print("server capabilities.extensions:", json.dumps(caps.get("extensions")))
        save("server_capabilities.json", caps)

        tools = dump(await c.list_tools())
        save("tools_list.json", tools)
        for t in tools["tools"]:
            print(f"tool {t['name']:<18} _meta.ui = {json.dumps(t.get('_meta', {}).get('ui'))}")

        res = dump(await c.list_resources())
        save("resources_list.json", res)
        for r in res["resources"]:
            print(f"resource {r['uri']}  mimeType={r['mimeType']}  _meta={json.dumps(r.get('_meta'))}")

        read = dump(await c.read_resource("ui://fernhill/order-board"))
        save("resource_read_order_board.json", read)
        content = read["contents"][0]
        (OUT / "order_board.html").write_text(content["text"])
        print(f"resources/read ui://fernhill/order-board -> mimeType={content['mimeType']}, "
              f"{len(content['text'])} characters, content _meta={json.dumps(content.get('_meta'))}")

        with_apps = dump(await c.call_tool("show_order_board", {}))
        save("call_show_order_board_apps_client.json", with_apps)
        print("\n[client WITH io.modelcontextprotocol/ui] show_order_board text:")
        print(with_apps["content"][0]["text"])
        print("structuredContent keys:", list(with_apps["structuredContent"].keys()),
              "orders:", len(with_apps["structuredContent"]["orders"]))

    async with Client(server.mcp) as c:
        plain = dump(await c.call_tool("show_order_board", {}))
        save("call_show_order_board_plain_client.json", plain)
        print("\n[client WITHOUT the extension] show_order_board text:")
        print(plain["content"][0]["text"])

        bad = dump(await c.call_tool("mark_order_done", {"order_id": "A-9999"}))
        save("call_mark_order_done_bad_id.json", bad)
        print("\nmark_order_done A-9999 -> isError:", bad.get("isError"), "|", bad["content"][0]["text"])

        # The in-process client bypasses any host: the server itself does not enforce visibility.
        good = dump(await c.call_tool("mark_order_done", {"order_id": "A-1043"}))
        save("call_mark_order_done_direct.json", good)
        print("mark_order_done A-1043 (direct, no host) ->", good["content"][0]["text"])
    shop_m08.ORDERS["A-1043"]["status"] = "ready"  # reset the in-memory shop


if __name__ == "__main__":
    asyncio.run(main())
