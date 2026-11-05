"""Module 10 demo, SDK client: the full OAuth flow done by mcp 2.3.0's OAuthClientProvider, headless.
The "browser" is a plain HTTP GET that reads the 302 Location (consent is automatic in the local AS).
Logs every HTTP request the SDK makes. Secrets are cut to 8 characters.

Run:  python demo_sdk.py                                   -> data/m10/sdk_flow.txt / .json
      python demo_sdk.py --label X --as-flag --sdk-defaults -> data/m10/sdk_flow_X.txt / .json
"""
import argparse
import json
import sys
import traceback
from urllib.parse import parse_qs, urlparse

import anyio
import httpx2

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import DATA, REDIRECT_URI, RS_URL, jwt_claims, red, servers  # noqa: E402
from demo_raw import red_url  # noqa: E402

from mcp import Client  # noqa: E402
from mcp.client.auth import OAuthClientProvider  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken  # noqa: E402

lines: list[str] = []
events: list[dict] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


class MemoryStorage:
    def __init__(self):
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info


def _body_summary(req: httpx2.Request) -> str | None:
    try:
        raw = req.content.decode()
    except Exception:
        return None
    if not raw:
        return None
    p = urlparse(str(req.url)).path
    if p == "/token":
        form = {k: v[0] for k, v in parse_qs(raw).items()}
        keep = {k: (red(v) if k in ("code", "code_verifier", "refresh_token", "client_secret") else v)
                for k, v in form.items() if k in ("grant_type", "resource", "scope", "code", "code_verifier",
                                                  "refresh_token")}
        return json.dumps(keep, ensure_ascii=False)
    if p == "/register":
        b = json.loads(raw)
        return json.dumps({k: b.get(k) for k in ("client_name", "application_type", "scope", "grant_types",
                                                  "token_endpoint_auth_method", "redirect_uris")}, ensure_ascii=False)
    if p == "/mcp":
        b = json.loads(raw)
        return f'method={b.get("method")} name={b.get("params", {}).get("name")}'
    return None


async def on_request(req: httpx2.Request):
    auth = req.headers.get("authorization")
    e = {"who": "sdk", "method": req.method, "url": red_url(str(req.url)),
         "authorization": ("Bearer " + red(auth[7:])) if auth else None, "body": _body_summary(req)}
    events.append(e)
    out(f"  sdk  > {req.method:<4} {red_url(str(req.url))}" + ("   [Authorization: " + e["authorization"] + "]"
                                                              if auth else ""))
    if e["body"]:
        out(f"             {e['body']}")


async def on_response(resp: httpx2.Response):
    events[-1]["status"] = resp.status_code
    wa = resp.headers.get("www-authenticate")
    events[-1]["www_authenticate"] = wa
    out(f"  sdk  < {resp.status_code}" + (f"   WWW-Authenticate: {wa}" if wa else ""))


class HeadlessBrowser:
    """redirect_handler + callback_handler for OAuthClientProvider, with no real browser."""

    def __init__(self):
        self.location: str | None = None

    async def redirect(self, authorization_url: str) -> None:
        q = {k: v[0] for k, v in parse_qs(urlparse(authorization_url).query).items()}
        out(f"  browser > GET /authorize  scope={q.get('scope')!r} resource={q.get('resource')!r} "
            f"code_challenge_method={q.get('code_challenge_method')}")
        async with httpx2.AsyncClient(follow_redirects=False) as b:
            r = await b.get(authorization_url)
        self.location = r.headers.get("location")
        events.append({"who": "browser", "method": "GET", "url": red_url(authorization_url), "status": r.status_code,
                       "location": red_url(self.location or ""), "scope": q.get("scope")})
        out(f"  browser < {r.status_code}  Location: {red_url(self.location or '')}")

    async def callback(self) -> AuthorizationCodeResult:
        q = {k: v[0] for k, v in parse_qs(urlparse(self.location or "").query).items()}
        if "error" in q and "code" not in q:
            # The SDK checks state and iss before it reads the code; give it the same values it would get.
            out(f"  browser   authorization error from AS: {q.get('error')}: {q.get('error_description')}")
            return AuthorizationCodeResult(code="", state=q.get("state"), iss=q.get("iss"))
        return AuthorizationCodeResult(code=q["code"], state=q.get("state"), iss=q.get("iss"))


async def run() -> dict:
    storage = MemoryStorage()
    browser = HeadlessBrowser()
    provider = OAuthClientProvider(
        server_url=RS_URL,
        client_metadata=OAuthClientMetadata(client_name="Fernhill SDK demo", redirect_uris=[REDIRECT_URI],
                                            grant_types=["authorization_code", "refresh_token"],
                                            response_types=["code"], token_endpoint_auth_method="none"),
        storage=storage, redirect_handler=browser.redirect, callback_handler=browser.callback)
    result: dict = {"steps": []}
    try:
        await _session(provider, result)
    except BaseException as e:  # noqa: BLE001  (connect-time failures arrive as an ExceptionGroup)
        leaf = e
        while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
            leaf = leaf.exceptions[0]
        msg = f"{type(leaf).__name__}: {leaf}"
        out(f"  EXCEPTION (connect/flow): {msg}")
        result["steps"].append({"call": "connect", "ok": False, "exception": msg})
    _final(storage, result)
    return result


async def _session(provider, result):
    async with httpx2.AsyncClient(auth=provider, timeout=30,
                                  event_hooks={"request": [on_request], "response": [on_response]}) as http:
        async with Client(streamable_http_client(RS_URL, http_client=http)) as client:
            out("\n--- client connected (mode auto: server/discover probe) ---")
            for label, coro in (("list_tools", lambda: client.list_tools()),
                                ("call_tool get_menu", lambda: client.call_tool("get_menu", {})),
                                ("call_tool refund A-1042", lambda: client.call_tool("refund", {"order_id": "A-1042"})),
                                ("call_tool get_menu again", lambda: client.call_tool("get_menu", {}))):
                out(f"\n--- {label} ---")
                try:
                    r = await coro()
                    if label == "list_tools":
                        summary = [t.name for t in r.tools]
                    else:
                        sc = r.structured_content
                        if isinstance(sc, dict) and isinstance(sc.get("result"), list):
                            summary = {"isError": r.is_error,
                                       "structured_content": [f"{d['drink']} ${d['price']:.2f}" for d in sc["result"]]}
                        else:
                            summary = {"isError": r.is_error,
                                       "text": " ".join(getattr(c, "text", "") for c in r.content)[:120]}
                    out(f"  result: {json.dumps(summary, ensure_ascii=False)}")
                    result["steps"].append({"call": label, "ok": not getattr(r, "is_error", False), "result": summary})
                except Exception as e:  # noqa: BLE001
                    msg = f"{type(e).__name__}: {e}"
                    out(f"  EXCEPTION: {msg}")
                    tb = traceback.format_exception(e)
                    result["steps"].append({"call": label, "ok": False, "exception": msg,
                                            "traceback_tail": "".join(tb[-3:])})
                    break


def _final(storage, result):
    if storage.tokens:
        c = jwt_claims(storage.tokens.access_token)
        result["final_token"] = {"scope_field": storage.tokens.scope, "has_refresh_token": bool(storage.tokens.refresh_token),
                                 "claims": {k: c.get(k) for k in ("iss", "sub", "aud", "scope")}}
        out(f"\nfinal stored token: scope={storage.tokens.scope!r} refresh_token="
            f"{red(storage.tokens.refresh_token)} claims={json.dumps(result['final_token']['claims'])}")
    if storage.client_info:
        result["client_info"] = {"application_type": storage.client_info.application_type,
                                 "issuer_binding": storage.client_info.issuer,
                                 "registered_scope": storage.client_info.scope}
        out(f"stored client registration: {json.dumps(result['client_info'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--as-flag", action="append", default=[])
    a = ap.parse_args()
    suffix = f"_{a.label}" if a.label else ""
    out(f"MCP masterclass · module 10 · SDK client OAuth flow (mcp 2.3.0 OAuthClientProvider) "
        f"AS flags={a.as_flag or ['(none: 2026-07-28 behaviour)']}")
    out(f"server {RS_URL}; secrets cut to 8 characters")
    with servers(as_flags=tuple(a.as_flag), log_name=f"sdk{suffix}"):
        res = anyio.run(run)
    res["events"] = events
    res["as_flags"] = a.as_flag
    authorize_scopes = [e["scope"] for e in events if e.get("who") == "browser"]
    res["authorize_scopes"] = authorize_scopes
    out(f"\nscopes the SDK asked for at /authorize, in order: {authorize_scopes}")
    out(f"HTTP requests made by the SDK: {sum(1 for e in events if e['who'] == 'sdk')}; browser legs: "
        f"{len(authorize_scopes)}")
    (DATA / f"sdk_flow{suffix}.txt").write_text("\n".join(lines) + "\n")
    (DATA / f"sdk_flow{suffix}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {DATA / f'sdk_flow{suffix}.txt'}")


if __name__ == "__main__":
    main()
