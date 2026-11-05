"""An MCP client with no SDK: one tool call on the 2026-07-28 spec is one HTTP POST."""
import json, sys
import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8142/mcp"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "raw", "version": "1"}}

def call(method, params=None, name=None, id=1):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name: headers["Mcp-Name"] = name
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": {**(params or {}), "_meta": META}}
    r = httpx.post(URL, headers=headers, json=body)
    return r.json()

tools = call("tools/list")["result"]["tools"]
print("tools:", [t["name"] for t in tools])
result = call("tools/call", {"name": "get_price", "arguments": {"drink": "latte"}}, name="get_price", id=2)
print("result:", result["result"]["structuredContent"])
