"""A small load balancer for the Tasks demo. Usage: lb.py rr|affinity PORT LOGFILE NAME=PORT [NAME=PORT ...]
rr        round robin, no memory (ordinary HTTP infrastructure)
affinity  round robin, but tasks/get|update|cancel go to the copy that created the task. It reads the
          Mcp-Name header (= taskId, a MUST in the Tasks spec) and learns taskId -> copy from the tools/call answer.
Passive health check: a copy that refuses a connection is marked down. Every answer gets an `x-copy` header."""
import itertools, json, sys, time
import httpx, uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

MODE, PORT, LOG = sys.argv[1], int(sys.argv[2]), open(sys.argv[3], "a", buffering=1)
NAMES = [a.split("=")[0] for a in sys.argv[4:]]
BACKENDS = [f"http://127.0.0.1:{a.split('=')[1]}" for a in sys.argv[4:]]
down, pin, rr = set(), {}, itertools.cycle(range(len(BACKENDS)))
http = httpx.AsyncClient(timeout=120)

async def proxy(request):
    body = await request.body()
    method, name = request.headers.get("mcp-method", "?"), request.headers.get("mcp-name")
    sticky = MODE == "affinity" and method.startswith("tasks/") and name in pin
    first = pin[name] if sticky else next(rr)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    for i in [(first + k) % len(BACKENDS) for k in range(len(BACKENDS))]:
        if i in down: continue
        try:
            r = await http.request(request.method, BACKENDS[i] + request.url.path, headers=headers, content=body)
        except httpx.ConnectError:
            down.add(i); continue
        if MODE == "affinity" and method == "tools/call":
            try:
                res = r.json().get("result", {})
                if res.get("resultType") == "task": pin[res["taskId"]] = i
            except Exception: pass
        LOG.write(json.dumps({"t": time.time(), "copy": NAMES[i], "http": r.status_code, "method": method,
                              "name": (name or "")[:13], "routed_by": "mcp-name" if sticky else "round-robin"}) + "\n")
        out = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding")}
        out["x-copy"] = NAMES[i]
        return Response(r.content, status_code=r.status_code, headers=out)
    LOG.write(json.dumps({"t": time.time(), "copy": None, "http": 502, "method": method}) + "\n")
    return Response(b"no live copy", status_code=502)

app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST", "DELETE"])])
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
