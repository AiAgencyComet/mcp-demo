"""A 25-line MCP gateway that decides from headers only (2026-07-28 Mcp-Method / Mcp-Name).
Rule: the kiosk client may read the menu and prices, but it may not call refund. Usage: gateway.py PORT UPSTREAM_PORT
It first rejects any request without the current MCP-Protocol-Version: older requests do not carry Mcp-Name rules the server checks,
and the spec says an intermediary SHOULD reject them rather than trust unvalidated header values."""
import sys, httpx, uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

PORT, UP = int(sys.argv[1]), f"http://127.0.0.1:{sys.argv[2]}"
BLOCK, VERSIONS = {"kiosk": {"refund"}}, {"2026-07-28"}
http = httpx.AsyncClient()

async def gate(request):
    if request.headers.get("mcp-protocol-version") not in VERSIONS:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "gateway: MCP-Protocol-Version 2026-07-28 required"}}, 400)
    client = request.headers.get("x-fernhill-client", "")
    method, name = request.headers.get("mcp-method"), request.headers.get("mcp-name")
    if method == "tools/call" and name in BLOCK.get(client, set()):
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": f"gateway: '{client}' may not call {name}"}}, 403)
    body = await request.body()
    r = await http.post(UP + request.url.path, content=body, headers={k: v for k, v in request.headers.items() if k != "host"})
    return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))

uvicorn.run(Starlette(routes=[Route("/mcp", gate, methods=["POST"])]), host="127.0.0.1", port=PORT, log_level="warning")
