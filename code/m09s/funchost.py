"""A local model of a serverless platform: every HTTP request starts a FRESH server process ("cold start"),
gets one response, and the process is stopped. Nothing survives in memory between requests.
Usage: funchost.py PORT LOGFILE -- SERVER_COMMAND... (the literal word PORT in the command is replaced by a free port)
Log: one JSON line per request: method, cold_ms (start until the port opens), total_ms, status."""
import json, os, socket, subprocess, sys, time
import httpx, uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

PORT, LOG = int(sys.argv[1]), open(sys.argv[2], "a", buffering=1)
CMD = sys.argv[sys.argv.index("--") + 1:]
http = httpx.AsyncClient(timeout=30)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def wait_port(p, limit=20.0):
    end = time.time() + limit
    while time.time() < end:
        try: socket.create_connection(("127.0.0.1", p), 0.05).close(); return True
        except OSError: time.sleep(0.01)
    return False

async def handle(request):
    t0 = time.perf_counter(); body = await request.body(); p = free_port()
    proc = subprocess.Popen([a.replace("PORT", str(p)) for a in CMD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
    try:
        if not wait_port(p): return Response(b"cold start failed", status_code=502)
        cold = (time.perf_counter() - t0) * 1000
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        r = await http.request(request.method, f"http://127.0.0.1:{p}{request.url.path}", headers=headers, content=body)
        out = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding")}
        out["x-instance"] = str(proc.pid)
        try: method = request.headers.get("mcp-method") or json.loads(body).get("method", "?")
        except Exception: method = request.method
        LOG.write(json.dumps({"t": time.time(), "method": method, "status": r.status_code, "cold_ms": round(cold, 1),
                              "total_ms": round((time.perf_counter() - t0) * 1000, 1), "pid": proc.pid}) + "\n")
        return Response(r.content, status_code=r.status_code, headers=out)
    finally:
        proc.terminate()
        try: proc.wait(5)
        except Exception: proc.kill()

app = Starlette(routes=[Route("/{path:path}", handle, methods=["GET", "POST", "DELETE"])])
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
