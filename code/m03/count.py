"""Count the HTTP requests and bytes that ONE tool call needs, old spec vs new spec, with no SDK.
Usage: count.py OLD_URL NEW_URL  -> data/m03/count.json"""
import json, sys
import httpx
from pathlib import Path

OLD, NEW = sys.argv[1], sys.argv[2]
OUT = Path(__file__).resolve().parents[2] / "data" / "m03" / "count.json"
log = []

def post(url, body, headers):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **headers}
    raw = json.dumps(body).encode()
    r = httpx.post(url, headers=h, content=raw)
    log.append({"spec": SPEC, "method": body.get("method"), "status": r.status_code,
                "sent": len(raw) + sum(len(k) + len(v) + 4 for k, v in h.items()),
                "received": len(r.content) + sum(len(k) + len(v) + 4 for k, v in r.headers.items())})
    return r

# OLD spec 2025-11-25: initialize, then initialized notification, then the call, all bound to a session id
SPEC = "old"
r = post(OLD, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "raw", "version": "1"}}}, {})
sid = r.headers["mcp-session-id"]
S = {"Mcp-Session-Id": sid, "MCP-Protocol-Version": "2025-11-25"}
post(OLD, {"jsonrpc": "2.0", "method": "notifications/initialized"}, S)
r = post(OLD, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_price", "arguments": {"drink": "latte"}}}, S)
old_answer = r.text.strip().splitlines()[-1]
r = httpx.delete(OLD, headers=S)  # end the session (the old spec asks clients to do this)
log.append({"spec": "old", "method": "DELETE session", "status": r.status_code,
            "sent": sum(len(k) + len(v) + 4 for k, v in S.items()),
            "received": len(r.content) + sum(len(k) + len(v) + 4 for k, v in r.headers.items())})

# NEW spec 2026-07-28: the call alone
SPEC = "new"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "raw", "version": "1"}}
r = post(NEW, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "get_price", "arguments": {"drink": "latte"}, "_meta": META}},
         {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call", "Mcp-Name": "get_price"})
new_answer = r.text

summary = {s: {"requests": sum(1 for x in log if x["spec"] == s),
               "bytes_sent": sum(x["sent"] for x in log if x["spec"] == s),
               "bytes_received": sum(x["received"] for x in log if x["spec"] == s)} for s in ("old", "new")}
OUT.write_text(json.dumps({"log": log, "summary": summary, "old_answer": old_answer, "new_answer": new_answer}, indent=1))
for x in log: print(x)
print(json.dumps(summary))
