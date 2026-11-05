"""A plain load balancer. Usage: lb.py rr|sticky PORT LOGFILE BACKEND_PORT...
rr     = round robin, no memory (what ordinary HTTP infrastructure does)
sticky = pins each Mcp-Session-Id to the copy that created it (what the old spec needed)
Both modes do a passive health check: a copy that refuses a connection is marked down and the
request goes to the next live copy (like nginx proxy_next_upstream error)."""
import itertools, json, sys, time
import httpx, uvicorn
from starlette.applications import Starlette
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

MODE, PORT, LOG = sys.argv[1], int(sys.argv[2]), open(sys.argv[3], "a", buffering=1)
BACKENDS = [f"http://127.0.0.1:{p}" for p in sys.argv[4:]]
down, pin, rr = set(), {}, itertools.cycle(range(len(BACKENDS)))
http = httpx.AsyncClient(timeout=30)

def mcp_method(request, body):
    m = request.headers.get("mcp-method")
    if m: return m
    try: return json.loads(body).get("method", "?")
    except Exception: return request.method

async def proxy(request):
    body, sid = await request.body(), request.headers.get("mcp-session-id")
    first = pin[sid] if (MODE == "sticky" and sid in pin) else next(rr)
    order = [(first + k) % len(BACKENDS) for k in range(len(BACKENDS))]
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    for i in order:
        if i in down: continue
        try:
            r = await http.send(http.build_request(request.method, BACKENDS[i] + request.url.path,
                                headers=headers, content=body, params=request.query_params), stream=True)
        except httpx.ConnectError:
            down.add(i); continue
        new_sid = r.headers.get("mcp-session-id")
        if new_sid and MODE == "sticky": pin.setdefault(new_sid, i)
        LOG.write(json.dumps({"t": time.time(), "copy": i, "status": r.status_code, "method": mcp_method(request, body),
                              "sid": (sid or new_sid or "")[:8]}) + "\n")
        out = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "connection")}
        out["x-copy"] = str(i)
        async def stream(r=r):
            async for chunk in r.aiter_raw(): yield chunk
            await r.aclose()
        return StreamingResponse(stream(), status_code=r.status_code, headers=out)
    LOG.write(json.dumps({"t": time.time(), "copy": None, "status": 502, "method": mcp_method(request, body)}) + "\n")
    return Response(b"no live copy", status_code=502)

app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST", "DELETE"])])
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
