"""The Fernhill MCP server as an OAuth 2.1 resource server, with one scope per tool. Spec 2026-07-28, mcp 2.3.0.

  get_menu, order_status -> menu:read     place_order -> orders:write     refund -> refunds:write

The SDK gives: bearer-token parsing, the RFC 8707 audience check, and the RFC 9728 metadata route.
The SDK's `required_scopes` is ONE list for the whole server, so this file adds a small gate that reads
the 2026-07-28 `Mcp-Method` / `Mcp-Name` headers (no body parse) and answers, before the tool runs:
  401 + WWW-Authenticate: Bearer resource_metadata="...", scope="..."            (no token / bad token)
  403 + WWW-Authenticate: Bearer error="insufficient_scope", scope="...", ...    (token lacks the scope)
Each tool checks its scope again from the verified token (defense in depth).

Run:  python server.py                 (per-tool scopes, spec-shaped challenges)
      python server.py --sdk-defaults  (SDK behaviour only: one server-wide scope, SDK challenge headers)
      python server.py --sdk-defaults --no-tool-check   (and no in-tool scope check either)
"""
import json
import logging
import sys
from typing import Literal

import anyio
import jwt
import uvicorn
from pydantic import BaseModel, Field
from starlette.datastructures import Headers
from starlette.middleware import Middleware

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import shop  # noqa: E402  (a copy of code/fernhill/shop.py)
from common import BASE_SCOPES, ISSUER, PRM_URL, RS_PORT, RS_URL, TOOL_SCOPES, url  # noqa: E402

SDK_DEFAULTS = "--sdk-defaults" in sys.argv
NO_TOOL_CHECK = "--no-tool-check" in sys.argv     # drop the in-tool scope check (shows the SDK-only result)
log = logging.getLogger("fernhill.auth")
logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")


class JWTVerifier:
    """TokenVerifier: check the AS signature (keys from its JWKS), `iss`, `exp`, and `aud` == this server."""

    def __init__(self):
        self.jwks = jwt.PyJWKClient(f"{ISSUER}/jwks")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = await anyio.to_thread.run_sync(self.jwks.get_signing_key_from_jwt, token)
            c = jwt.decode(token, key.key, algorithms=["ES256"], issuer=ISSUER, audience=RS_URL,
                           options={"require": ["iss", "aud", "exp", "sub"]})
        except jwt.PyJWTError as e:
            log.info("token refused: %s: %s", type(e).__name__, e)
            return None
        return AccessToken(token=token, client_id=c["client_id"], scopes=c["scope"].split(), expires_at=c["exp"],
                           resource=c["aud"], subject=c["sub"], claims=c)


mcp = MCPServer(
    "fernhill",
    instructions="Tools for the Fernhill Coffee shop: menu, orders and refunds.",
    token_verifier=JWTVerifier(),
    auth=AuthSettings(
        issuer_url=url(ISSUER),
        resource_server_url=url(RS_URL),
        validate_token_resource=True,              # SDK also refuses a token whose resource is not RS_URL
        required_scopes=BASE_SCOPES if SDK_DEFAULTS else None,
    ),
)


def caller(ctx: Context) -> AccessToken:
    tok, via = get_access_token(), "get_access_token()"
    if tok is None:                                   # fall back to the Starlette request in the context
        user = ctx.request_context.request.scope.get("user")
        tok, via = (user.access_token if isinstance(user, AuthenticatedUser) else None), "request.scope['user']"
    log.info("tool sees token via %s: sub=%s scopes=%s", via, tok and tok.subject, tok and tok.scopes)
    if tok is None:
        raise ToolError("No verified token for this request.")
    return tok


def need(ctx: Context, tool: str) -> AccessToken:
    tok = caller(ctx)
    if NO_TOOL_CHECK:
        return tok
    missing = [s for s in TOOL_SCOPES[tool] if s not in tok.scopes]
    if missing:
        raise ToolError(f"This token does not have the scope {' '.join(missing)}.")
    return tok


# ---------- tools (same shapes as code/fernhill/server.py; refund has no confirm step here) ----------

class MenuItem(BaseModel):
    drink: str
    price: float = Field(description="Price in US dollars")
    sizes: list[str]


@mcp.tool()
def get_menu(ctx: Context) -> list[MenuItem]:
    """Return every item on the Fernhill menu with its price and sizes. Scope: menu:read."""
    need(ctx, "get_menu")
    return [MenuItem(drink=d, **v) for d, v in shop.MENU.items()]


class Item(BaseModel):
    drink: str = Field(description="A drink name from get_menu")
    size: str
    milk: Literal["whole", "oat", "none"] = "whole"


class Order(BaseModel):
    order_id: str
    total: float
    status: str


@mcp.tool()
def place_order(items: list[Item], name: str, ctx: Context) -> Order:
    """Place a pickup order. Returns an order_id. Scope: orders:write."""
    need(ctx, "place_order")
    for it in items:
        if it.drink not in shop.MENU:
            raise ToolError(f"'{it.drink}' is not on the menu. Call get_menu to see the menu.")
    total = round(sum(shop.MENU[i.drink]["price"] + (0.60 if i.milk == "oat" else 0) for i in items), 2)
    order_id = f"A-{1041 + len(shop.ORDERS)}"
    shop.ORDERS[order_id] = {"items": [i.model_dump() for i in items], "total": total, "status": "making",
                             "handoff": {"kind": "pickup", "name": name}}
    return Order(order_id=order_id, total=total, status="making")


@mcp.tool()
def order_status(order_id: str, ctx: Context) -> Order:
    """Return the status of one order. Scope: menu:read."""
    need(ctx, "order_status")
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}. Order IDs look like A-1041.")
    o = shop.ORDERS[order_id]
    return Order(order_id=order_id, total=o["total"], status=o["status"])


@mcp.tool()
def refund(order_id: str, ctx: Context) -> str:
    """Refund one order. Scope: refunds:write."""
    tok = need(ctx, "refund")
    if order_id not in shop.ORDERS:
        raise ToolError(f"No order {order_id}.")
    shop.ORDERS[order_id]["status"] = "refunded"
    return (f"Refunded ${shop.ORDERS[order_id]['total']:.2f} for {order_id} "
            f"(person: {tok.subject}, client: {tok.client_id[:8]}).")


# ---------- the per-tool scope gate (HTTP layer, before the tool runs) ----------

def _challenge(params: list[tuple[str, str]]) -> bytes:
    return ("Bearer " + ", ".join(f'{k}="{v}"' for k, v in params)).encode()


class ToolScopeGate:
    """Runs after the SDK's AuthenticationMiddleware (so scope["user"] is set) and before routing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/mcp" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        h = Headers(scope=scope)
        method, name = h.get("mcp-method"), h.get("mcp-name")
        needed = TOOL_SCOPES.get(name, []) if method == "tools/call" else []
        user = scope.get("user")

        if not isinstance(user, AuthenticatedUser):
            sent_token = h.get("authorization", "").lower().startswith("bearer ")
            params = [("resource_metadata", PRM_URL), ("scope", " ".join(needed or BASE_SCOPES))]
            if sent_token:   # RFC 6750 §3.1: an error code only when the request carried a token
                params = [("error", "invalid_token"),
                          ("error_description", "The access token is not valid for this server")] + params
                body = {"error": "invalid_token"}
            else:
                body = {"message": "This MCP server needs an access token. See WWW-Authenticate."}
            log.info("401 %s %s token_sent=%s", method, name, sent_token)
            return await self._send(send, 401, _challenge(params), body)

        missing = [s for s in needed if s not in user.scopes]
        if missing:
            params = [("error", "insufficient_scope"), ("scope", " ".join(needed)),
                      ("resource_metadata", PRM_URL),
                      ("error_description", f"The tool {name} needs the scope {' '.join(needed)}")]
            log.info("403 %s %s has=%s needs=%s", method, name, user.scopes, needed)
            return await self._send(send, 403, _challenge(params),
                                    {"error": "insufficient_scope", "scope": " ".join(needed)})
        return await self.app(scope, receive, send)

    @staticmethod
    async def _send(send, status: int, www_auth: bytes, body: dict):
        data = json.dumps(body).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
                                (b"www-authenticate", www_auth), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": data})


def build_app():
    app = mcp.streamable_http_app(host="127.0.0.1")
    if SDK_DEFAULTS:
        return app
    app.user_middleware.append(Middleware(ToolScopeGate))   # innermost user middleware: after auth
    # Replace the SDK metadata route: the SDK fills scopes_supported from required_scopes (None here).
    prm = create_protected_resource_routes(resource_url=url(RS_URL), authorization_servers=[url(ISSUER)],
                                           scopes_supported=BASE_SCOPES, resource_name="Fernhill Coffee MCP server")[0]
    app.router.routes = [prm if getattr(r, "path", None) == prm.path else r for r in app.router.routes]
    return app


if __name__ == "__main__":
    print(f"RS {RS_URL} mode={'sdk-defaults' if SDK_DEFAULTS else 'per-tool-scopes'}", flush=True)
    uvicorn.run(build_app(), host="127.0.0.1", port=RS_PORT, log_level="info")
