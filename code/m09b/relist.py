"""A host that re-lists tools before every turn (to stay fresh). Count what reaches the server, ttlMs 0 vs 300000.
Runs through the m09 load balancer only to log every HTTP request. -> data/m09b/relist.json"""
import asyncio, json, socket, subprocess, sys, time
from pathlib import Path
from mcp import Client
ROOT = Path(__file__).resolve().parents[2]; CODE = ROOT / "code"; PY = CODE / ".venv-new/bin/python"
def wait(p):
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)
async def host(url, turns):
    t_list = 0.0
    async with Client(url) as c:
        for _ in range(turns):
            t0 = time.perf_counter(); await c.list_tools(); t_list += time.perf_counter() - t0
            await c.call_tool("get_price", {"drink": "latte"})
    return t_list * 1000
out = {}
for ttl in (0, 300000):
    log = ROOT / f"data/m09b/lb_ttl{ttl}.jsonl"; log.unlink(missing_ok=True)
    srv = subprocess.Popen([PY, Path(__file__).parent / "server_ttl.py", "8231", str(ttl)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); wait(8231)
    lb = subprocess.Popen([PY, CODE / "m09/lb.py", "rr", "8230", log, "8231"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); wait(8230)
    ms = asyncio.run(host("http://127.0.0.1:8230/mcp", 20))
    for p in (lb, srv): p.terminate(); p.wait(5)
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    out[ttl] = {"turns": 20, "tools_list_requests": sum(r["method"] == "tools/list" for r in rows),
                "tools_call_requests": sum(r["method"] == "tools/call" for r in rows), "all_requests": len(rows), "list_ms_total": round(ms, 1)}
    print(f"ttlMs={ttl:6}: {out[ttl]}")
(ROOT / "data/m09b/relist.json").write_text(json.dumps(out, indent=1))
