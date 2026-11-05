"""Does this machine's Claude Code declare the Tasks extension? No model call: the Anthropic API URL points at a
closed local port, so only the MCP connection happens. Usage: host_probe.py
Add --live for a real run (a model call; NOT run by the builder). Starts one Fernhill copy (8181) and a capture proxy (8183) that records, per request: method, Mcp-* headers,
protocolVersion, clientCapabilities, clientInfo. No other header is logged. Writes data/m07b/host_probe.json."""
import json, os, socket, subprocess, sys, tempfile, threading, time
from pathlib import Path
import httpx, uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m07b"
PY = str(CODE / ".venv-new/bin/python"); BACK, PROXY = 8181, 8183
seen = []

async def proxy(request):
    body = await request.body()
    try:
        msg = json.loads(body) if body else {}
        meta = (msg.get("params") or {}).get("_meta") or {}
        seen.append({"t": round(time.time(), 3), "http_method": request.method, "jsonrpc_method": msg.get("method"),
                     "mcp_headers": {k: v for k, v in request.headers.items() if k.lower().startswith("mcp")},
                     "user_agent": request.headers.get("user-agent"),
                     "protocolVersion": meta.get("io.modelcontextprotocol/protocolVersion") or (msg.get("params") or {}).get("protocolVersion"),
                     "clientCapabilities": meta.get("io.modelcontextprotocol/clientCapabilities") or (msg.get("params") or {}).get("capabilities"),
                     "clientInfo": meta.get("io.modelcontextprotocol/clientInfo") or (msg.get("params") or {}).get("clientInfo")})
    except Exception as e:
        seen.append({"http_method": request.method, "parse_error": str(e)})
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.request(request.method, f"http://127.0.0.1:{BACK}{request.url.path}", headers=headers, content=body)
    out = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding")}
    return Response(r.content, status_code=r.status_code, headers=out)

def wait(p):
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)

for f in (HERE / "run").glob("probe.db*"): f.unlink()
server = subprocess.Popen([PY, "server.py", str(BACK), "A", "shared", str(HERE / "run/probe.db")], cwd=HERE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait(BACK)
cfg = uvicorn.Config(Starlette(routes=[Route("/{p:path}", proxy, methods=["GET", "POST", "DELETE"])]), host="127.0.0.1", port=PROXY, log_level="warning")
srv = uvicorn.Server(cfg); threading.Thread(target=srv.run, daemon=True).start(); wait(PROXY)
mcpcfg = Path(tempfile.mkdtemp()) / "probe.mcp.json"
mcpcfg.write_text(json.dumps({"mcpServers": {"fernhill": {"type": "http", "url": f"http://127.0.0.1:{PROXY}/mcp"}}}))
LIVE = "--live" in sys.argv   # NOT run by the builder: a real model call (costs usage), to see Claude Code poll the task
env = dict(os.environ) if LIVE else {**os.environ, "ANTHROPIC_BASE_URL": "http://127.0.0.1:9"}   # closed port: no model call
try:
    cc = subprocess.run(["claude", "-p", "Use export_sales_report with days 20.", "--mcp-config", str(mcpcfg), "--strict-mcp-config"]
                        + (["--model", "haiku", "--allowedTools", "mcp__fernhill__export_sales_report"] if LIVE else []),
                        env=env, capture_output=True, text=True, timeout=120 if LIVE else 60, cwd=tempfile.gettempdir())
    exit_info = {"exit": cc.returncode, "stdout_tail": cc.stdout[-300:], "stderr_tail": cc.stderr[-300:]}
except subprocess.TimeoutExpired:
    exit_info = {"exit": "timeout after 60 s"}
finally:
    server.terminate()
    try: server.wait(10)
    except subprocess.TimeoutExpired: server.kill(); server.wait()
    srv.should_exit = True; time.sleep(0.5)
version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
out = {"claude_code_version": version, "claude_run": exit_info, "requests": seen}
(DATA / ("host_probe_live.json" if LIVE else "host_probe.json")).write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2)[:3000])
