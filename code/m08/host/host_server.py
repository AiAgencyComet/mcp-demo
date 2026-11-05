"""A small LOCAL test host for MCP Apps (spec 2026-01-26), for module 8. Two origins on loopback:

  host page   http://127.0.0.1:8820   host.html + /api/mcp (forwards the page's JSON-RPC) + /api/log
  sandbox     http://localhost:8821   sandbox.html, served with a CSP header built from the
                                      resource's _meta.ui.csp (the spec's sandbox proxy)

The host page builds raw JSON-RPC for the MCP server (Streamable HTTP, spec 2026-07-28) and declares
MCP Apps support in clientCapabilities; this backend only forwards it. Nothing listens on a public interface.
Usage: python host_server.py http://127.0.0.1:8810/mcp
"""
import asyncio
import contextlib
import json
import re
import signal
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

HERE = Path(__file__).parent
DATA = HERE.resolve().parents[2] / "data" / "m08"
MCP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8810/mcp"
HOST_PORT, SANDBOX_PORT = 8820, 8821

http = httpx.AsyncClient(timeout=30)


# ---------- host origin: 127.0.0.1:8820 ----------

async def index(_: Request):
    return FileResponse(HERE / "host.html")


async def api_mcp(request: Request):
    """Forward one JSON-RPC message, built by the host page, to the MCP server unchanged.
    (The page cannot reach the MCP server itself: it is another origin.) Return the wire response."""
    body = await request.json()
    wire = body["wire"]
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    headers |= {k: v for k, v in body["headers"].items() if k.lower().startswith("mcp")}
    t0 = time.perf_counter()
    r = await http.post(MCP_URL, headers=headers, json=wire)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return JSONResponse({"status": r.status_code, "response": r.json(), "ms": ms})


def log_file(request: Request) -> Path:
    name = request.query_params.get("name", "bridge_log")
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name):
        name = "bridge_log"
    return DATA / f"{name}.jsonl"


async def api_log(request: Request):
    entry = await request.json()
    with log_file(request).open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return JSONResponse({"ok": True})


async def api_log_reset(request: Request):
    DATA.mkdir(parents=True, exist_ok=True)
    log_file(request).write_text("")
    return JSONResponse({"ok": True})


host_app = Starlette(routes=[
    Route("/", index),
    Route("/api/mcp", api_mcp, methods=["POST"]),
    Route("/api/log", api_log, methods=["POST"]),
    Route("/api/log/reset", api_log_reset, methods=["POST"]),
])


# ---------- sandbox origin: localhost:8821 ----------

def build_csp(csp: dict | None) -> str:
    """CSP for the sandbox document. No ui.csp -> the spec's restrictive default."""
    if not csp:
        parts = ["default-src 'none'", "script-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline'",
                 "img-src 'self' data:", "media-src 'self' data:", "connect-src 'none'"]
    else:
        res = " ".join(csp.get("resourceDomains") or [])
        con = " ".join(csp.get("connectDomains") or [])
        parts = ["default-src 'none'", f"script-src 'self' 'unsafe-inline' {res}".strip(),
                 f"style-src 'self' 'unsafe-inline' {res}".strip(), f"connect-src 'self' {con}".strip(),
                 f"img-src 'self' data: {res}".strip(), f"font-src 'self' {res}".strip(),
                 f"media-src 'self' data: {res}".strip()]
    frames = " ".join((csp or {}).get("frameDomains") or []) or "'none'"
    base = " ".join((csp or {}).get("baseUriDomains") or []) or "'self'"
    parts += [f"frame-src {frames}", "object-src 'none'", f"base-uri {base}"]
    return "; ".join(parts)


async def sandbox(request: Request):
    raw = request.query_params.get("csp")
    csp = json.loads(raw) if raw else None
    html = (HERE / "sandbox.html").read_text()
    return HTMLResponse(html, headers={"Content-Security-Policy": build_csp(csp)})


sandbox_app = Starlette(routes=[Route("/sandbox.html", sandbox)])


class Server(uvicorn.Server):
    """Two uvicorn servers share one process, so neither installs its own signal handlers."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def main():
    servers = [Server(uvicorn.Config(host_app, host="127.0.0.1", port=HOST_PORT, log_level="warning")),
               Server(uvicorn.Config(sandbox_app, host="127.0.0.1", port=SANDBOX_PORT, log_level="warning"))]
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [setattr(s, "should_exit", True) for s in servers])
    print(f"host    http://127.0.0.1:{HOST_PORT}/   -> MCP server {MCP_URL}", flush=True)
    print(f"sandbox http://localhost:{SANDBOX_PORT}/sandbox.html", flush=True)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
