"""Raw HTTP view of the MCP App on the wire (no SDK): server/discover, tools/list, resources/read.
The client says it supports MCP Apps in params._meta clientCapabilities.extensions.
Usage: python raw_http.py http://127.0.0.1:8810/mcp  > data/m08/raw_http_transcript.txt"""
import json
import sys

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8810/mcp"
CAPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": CAPS,
        "io.modelcontextprotocol/clientInfo": {"name": "raw-host", "version": "1"}}


def call(method, params=None, name=None, id=1):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": {**(params or {}), "_meta": META}}
    r = httpx.post(URL, headers=headers, json=body)
    print(f"$ POST {URL}")
    for k in ("MCP-Protocol-Version", "Mcp-Method", "Mcp-Name"):
        if k in headers:
            print(f"  {k}: {headers[k]}")
    print(f"  body: {json.dumps({k: v for k, v in body.items() if k != 'params'} | {'params': {k: v for k, v in body['params'].items() if k != '_meta'}})}")
    print(f"< HTTP {r.status_code}  content-type: {r.headers.get('content-type')}")
    return r.json()


d = call("server/discover")
print("  result.capabilities.extensions =", json.dumps(d["result"]["capabilities"].get("extensions")))
print("  result.supportedVersions =", d["result"].get("supportedVersions"), "\n")

t = call("tools/list", id=2)
for tool in t["result"]["tools"]:
    print(f"  tool {tool['name']}: _meta = {json.dumps(tool.get('_meta'))}")
print(f"  ttlMs={t['result'].get('ttlMs')} cacheScope={t['result'].get('cacheScope')}\n")

lr = call("resources/list", id=3)
for res in lr["result"]["resources"]:
    print(f"  resource {res['uri']}: mimeType={res['mimeType']} _meta={json.dumps(res.get('_meta'))}")
print()

rr = call("resources/read", {"uri": "ui://fernhill/order-board"}, name="ui://fernhill/order-board", id=4)
if "error" in rr:
    print("  error:", rr["error"])
else:
    c = rr["result"]["contents"][0]
    print(f"  contents[0].mimeType = {c['mimeType']}")
    print(f"  contents[0].text = {len(c['text'])} characters, starts {c['text'][:40]!r}")
    print(f"  contents[0]._meta = {json.dumps(c.get('_meta'))}\n")

tc = call("tools/call", {"name": "show_order_board", "arguments": {}}, name="show_order_board", id=5)
res = tc["result"]
print("  content[0].text =", json.dumps(res["content"][0]["text"])[:120] + "...")
print("  structuredContent.orders =", len(res["structuredContent"]["orders"]), "rows")
print("  _meta =", json.dumps(res.get("_meta")))
