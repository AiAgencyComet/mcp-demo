"""Run the gateway in front of the Fernhill server; three calls from the kiosk; time header-only vs body-parse decisions."""
import json, socket, subprocess, sys, time, timeit
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]; CODE = ROOT / "code"; PY = CODE / ".venv-new/bin/python"
def wait(p):
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)
srv = subprocess.Popen([PY, CODE / "fernhill/server.py", "http", "8241"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); wait(8241)
gw = subprocess.Popen([PY, Path(__file__).parent / "gateway.py", "8240", "8241"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); wait(8240)
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
        "io.modelcontextprotocol/clientInfo": {"name": "kiosk", "version": "1"}}
def call(name, args, header_name=None, version="2026-07-28"):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": version,
         "Mcp-Method": "tools/call", "Mcp-Name": header_name or name, "X-Fernhill-Client": "kiosk"}
    if version is None: h.pop("MCP-Protocol-Version")
    r = httpx.post("http://127.0.0.1:8240/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args, "_meta": META}})
    return r.status_code, r.json()
lines = []
for label, args in (("get_menu", ("get_menu", {})), ("refund", ("refund", {"order_id": "A-1041"})),
                    ("refund, header says get_menu", ("refund", {"order_id": "A-1041"}, "get_menu")),
                    ("get_menu, no version header", ("get_menu", {}, None, None)),
                    ("get_menu, version 2025-11-25", ("get_menu", {}, None, "2025-11-25"))):
    st, body = call(*args); msg = body.get("error", {}).get("message") or json.dumps(body.get("result", {}))[:90]
    lines.append(f"kiosk -> {label:30} HTTP {st}  {msg}")
for p in (gw, srv): p.terminate(); p.wait(5)
big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "place_order", "arguments": {"drink": "latte", "size": "large", "milk": "oat", "note": "x" * 380},
                  "_meta": META}}).encode()   # a typical request, about 0.5 KB
hdrs = {"mcp-method": "tools/call", "mcp-name": "place_order"}
t_head = timeit.timeit(lambda: hdrs.get("mcp-name") in {"refund"}, number=10000) / 10000 * 1e6
t_body = timeit.timeit(lambda: json.loads(big)["params"]["name"] in {"refund"}, number=20000) / 20000 * 1e6
lines.append(f"decision time for a {len(big)} B request: headers {t_head:.2f} µs  vs  parse body {t_body:,.0f} µs ({t_body/t_head:,.0f}x)")
print("\n".join(lines)); (ROOT / "data/m09b/gateway.txt").write_text("\n".join(lines) + "\n")
