"""Raw two-round refund call (no SDK). Prints both rounds. Usage: two_rounds.py URL [tamper]"""
import json, sys
import httpx

URL = sys.argv[1]; TAMPER = len(sys.argv) > 2 and sys.argv[2] == "tamper"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
        "io.modelcontextprotocol/clientInfo": {"name": "raw", "version": "1"}}
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
     "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call", "Mcp-Name": "refund"}
ARGS = {"order_id": "A-1042", "amount": 9.40}

def post(params, id):
    r = httpx.post(URL, headers=H, json={"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {**params, "_meta": META}})
    return r.headers.get("x-copy"), r.status_code, r.json()

copy1, st1, r1 = post({"name": "refund", "arguments": ARGS}, 1)
print(json.dumps({"round": 1, "copy": copy1, "status": st1, "body": r1}))
res = r1.get("result", {})
if res.get("resultType") != "input_required": sys.exit(0)
key = next(iter(res["inputRequests"]))
state = res["requestState"]
if TAMPER: state = state[:-6] + ("A" if state[-6] != "A" else "B") + state[-5:]
copy2, st2, r2 = post({"name": "refund", "arguments": ARGS, "requestState": state,
                       "inputResponses": {key: {"action": "accept", "content": {"confirm": True}}}}, 2)
print(json.dumps({"round": 2, "copy": copy2, "status": st2, "body": r2}))
