"""Module 10 demo, raw HTTP: OAuth 2.1 for an MCP server, step by step, with no SDK on the client side.
Starts the local AS and the Fernhill server, runs every step, stops both.
Writes data/m10/raw_flow.txt (transcript) and data/m10/raw_flow.json (every exchange, secrets cut to 8 chars)."""
import base64
import hashlib
import json
import re
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import (DATA, ISSUER, META, OTHER_RESOURCE, PV, REDIRECT_URI, RS_URL, jwt_claims, red,  # noqa: E402
                    servers)

SECRET_KEYS = {"access_token", "refresh_token", "code", "client_secret", "code_verifier", "state"}
lines: list[str] = []
exchanges: list[dict] = []
client = httpx.Client(timeout=20, follow_redirects=False)


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def red_obj(o):
    if isinstance(o, dict):
        return {k: (red(v) if k in SECRET_KEYS and isinstance(v, str) else red_obj(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [red_obj(v) for v in o]
    return o


def red_url(u: str) -> str:
    p = urlparse(u)
    if not p.query:
        return u
    q = [(k, red(v[0]) if k in SECRET_KEYS else v[0]) for k, v in parse_qs(p.query, keep_blank_values=True).items()]
    return p._replace(query=urlencode(q, safe=":/ ")).geturl().replace("%E2%80%A6", "…")


def red_headers(h: dict) -> dict:
    o = {}
    for k, v in h.items():
        if k.lower() == "authorization" and v.lower().startswith("bearer "):
            v = "Bearer " + red(v[7:])
        o[k] = v
    return o


def parse_body(r: httpx.Response):
    ct = r.headers.get("content-type", "")
    if "text/event-stream" in ct:
        data = [ln[5:].strip() for ln in r.text.splitlines() if ln.startswith("data:")]
        return json.loads(data[-1]) if data else r.text
    try:
        return r.json()
    except ValueError:
        return r.text


SHOW_RESP_HEADERS = ("www-authenticate", "location", "cache-control")


def http(step: str, method: str, url: str, *, headers=None, json_body=None, form=None, brief=None):
    headers = headers or {}
    r = client.request(method, url, headers=headers, json=json_body, data=form)
    body = parse_body(r)
    rec = {"step": step,
           "request": {"method": method, "url": red_url(url), "headers": red_headers(headers),
                       "json": red_obj(json_body), "form": red_obj(form)},
           "response": {"status": r.status_code, "reason": r.reason_phrase,
                        "headers": {k: (red_url(v) if k == "location" else v) for k, v in r.headers.items()},
                        "body": red_obj(body)}}
    exchanges.append(rec)
    p = urlparse(url)
    sp = urlparse(red_url(url))
    out(f"> {method} {sp.path}{('?' + sp.query) if sp.query else ''}   ({sp.scheme}://{sp.netloc})")
    for k, v in red_headers(headers).items():
        if k.lower() in ("authorization", "mcp-method", "mcp-name", "mcp-protocol-version"):
            out(f">   {k}: {v}")
    if json_body is not None and not str(p.path).endswith("/mcp"):
        out(">   " + json.dumps(red_obj(json_body), ensure_ascii=False))
    if form is not None:
        out(">   form: " + json.dumps(red_obj(form), ensure_ascii=False))
    out(f"< {r.status_code} {r.reason_phrase}")
    for k in SHOW_RESP_HEADERS:
        if k in r.headers:
            v = red_url(r.headers[k]) if k == "location" else r.headers[k]
            out(f"<   {k}: {v}")
    shown = brief(body) if brief else red_obj(body)
    if shown is not None:
        out("<   " + (shown if isinstance(shown, str) else json.dumps(shown, ensure_ascii=False)))
    return r, body


def mcp(step: str, method: str, params=None, name=None, token=None, id=1, brief=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": PV, "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    if token:
        h["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": {**(params or {}), "_meta": META}}
    return http(step, "POST", RS_URL, headers=h, json_body=body, brief=brief)


def www_auth_params(value: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', value))


def section(n: str, title: str) -> None:
    out("")
    out(f"=== {n}. {title} ===")


def check(label: str, ok: bool) -> None:
    out(f"    [{'ok' if ok else 'FAIL'}] {label}")
    if not ok:
        raise SystemExit(f"check failed: {label}")


def pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def authorize(as_md: dict, client_id: str, scope: str, resource: str, expected_issuer: str, step: str):
    """Authorization request (the browser leg, done headless) -> code. Returns (params, verifier)."""
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI, "scope": scope,
         "resource": resource, "code_challenge": challenge, "code_challenge_method": "S256", "state": state}
    r, _ = http(step, "GET", f"{as_md['authorization_endpoint']}?{urlencode(q)}", brief=lambda b: None)
    loc = urlparse(r.headers["location"])
    got = {k: v[0] for k, v in parse_qs(loc.query).items()}
    # RFC 9207 + MCP 2026-07-28: check iss BEFORE using code or error.
    if as_md.get("authorization_response_iss_parameter_supported"):
        check(f"iss is present and == recorded issuer by plain string compare ({got.get('iss')!r})",
              got.get("iss") == expected_issuer)
    check("state == the state we sent", got.get("state") == state)
    return got, verifier


def token_request(as_md: dict, form: dict, step: str):
    return http(step, "POST", as_md["token_endpoint"], form=form,
                brief=lambda b: {**red_obj(b)} if isinstance(b, dict) else b)


def show_claims(tok: str) -> dict:
    c = jwt_claims(tok)
    out("    access token claims (decoded for display): " + json.dumps(
        {k: c[k] for k in ("iss", "sub", "aud", "client_id", "scope", "exp")}))
    return c


def tool_names(b):
    return {"tools": [t["name"] for t in b["result"]["tools"]]} if isinstance(b, dict) and "result" in b else b


def call_result(b):
    if isinstance(b, dict) and "result" in b:
        res = b["result"]
        sc = res.get("structuredContent")
        if isinstance(sc, dict) and isinstance(sc.get("result"), list):   # get_menu: list of drinks
            return {"isError": res.get("isError", False),
                    "structuredContent": [f"{d['drink']} ${d['price']:.2f}" for d in sc["result"]]}
        txt = " ".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return {"isError": res.get("isError", False), "text": txt[:160] + ("…" if len(txt) > 160 else "")}
    return b


def main():
    out("MCP masterclass · module 10 · OAuth 2.1 for the Fernhill MCP server, raw HTTP (spec 2026-07-28)")
    out(f"Fernhill MCP server (resource server): {RS_URL}")
    out(f"Local authorization server:            {ISSUER}")
    out("Tokens, codes, state and secrets are cut to their first 8 characters.")

    section("1", "Call the server with no token")
    out(f"    (first MCP request body, full: {json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {'_meta': META}})})")
    r, _ = mcp("1 no token", "tools/list")
    check("HTTP 401", r.status_code == 401)
    ch = www_auth_params(r.headers["www-authenticate"])
    check("no error code in the challenge when no token was sent (RFC 6750 §3.1)", "error" not in ch)
    first_scope = ch["scope"]

    section("2", "Read the protected resource metadata (RFC 9728) from resource_metadata")
    r, prm = http("2 PRM", "GET", ch["resource_metadata"])
    check("resource == the URL we called (RFC 9728 §3.3)", prm["resource"] == RS_URL)
    issuer = prm["authorization_servers"][0]

    section("3", "Discover the authorization server metadata (RFC 8414) and record the issuer")
    r, as_md = http("3 AS metadata", "GET", f"{issuer}/.well-known/oauth-authorization-server")
    check("metadata issuer == the issuer we built the URL from (exact string)", as_md["issuer"] == issuer)
    check("code_challenge_methods_supported lists S256 (PKCE; else MUST refuse)",
          "S256" in as_md.get("code_challenge_methods_supported", []))
    out(f"    recorded issuer: {issuer!r}; authorization_response_iss_parameter_supported="
        f"{as_md.get('authorization_response_iss_parameter_supported')}")

    section("4", "Register the client (Dynamic Client Registration, application_type native)")
    reg = {"client_name": "Fernhill demo CLI", "redirect_uris": [REDIRECT_URI], "application_type": "native",
           "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
           "token_endpoint_auth_method": "none"}
    r, ci = http("4 DCR", "POST", as_md["registration_endpoint"], json_body=reg,
                 brief=lambda b: {k: b.get(k) for k in ("client_id", "application_type", "token_endpoint_auth_method",
                                                         "redirect_uris", "scope")})
    check("HTTP 201", r.status_code == 201)
    client_id = ci["client_id"]

    section("5", f"Authorization request: scope from the 401 challenge ({first_scope!r}), PKCE S256, resource")
    got, verifier = authorize(as_md, client_id, first_scope, RS_URL, issuer, "5 authorize menu:read")

    section("6", "Token request: code + code_verifier + resource")
    r, tok = token_request(as_md, {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
                                   "client_id": client_id, "code_verifier": verifier, "resource": RS_URL},
                           "6 token menu:read")
    check("HTTP 200", r.status_code == 200)
    t1 = tok["access_token"]
    c1 = show_claims(t1)
    check("aud == the Fernhill server URI (RFC 8707)", c1["aud"] == RS_URL)

    section("7", "tools/list with the menu:read token")
    r, _ = mcp("7 tools/list", "tools/list", token=t1, brief=tool_names)
    check("HTTP 200", r.status_code == 200)

    section("8", "tools/call get_menu with the menu:read token")
    r, _ = mcp("8 get_menu", "tools/call", {"name": "get_menu", "arguments": {}}, name="get_menu", token=t1, id=2,
               brief=call_result)
    check("HTTP 200", r.status_code == 200)

    section("9", "tools/call refund with the menu:read token")
    r, _ = mcp("9 refund refused", "tools/call", {"name": "refund", "arguments": {"order_id": "A-1041"}},
               name="refund", token=t1, id=3, brief=call_result)
    check("HTTP 403", r.status_code == 403)
    ch2 = www_auth_params(r.headers["www-authenticate"])
    check('error="insufficient_scope"', ch2.get("error") == "insufficient_scope")
    union = " ".join(dict.fromkeys(first_scope.split() + ch2["scope"].split()))

    section("10", f"Step-up: ask for the UNION of old and challenged scopes ({union!r})")
    got, verifier = authorize(as_md, client_id, union, RS_URL, issuer, "10 authorize union")
    r, tok = token_request(as_md, {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
                                   "client_id": client_id, "code_verifier": verifier, "resource": RS_URL},
                           "10 token union")
    t2 = tok["access_token"]
    show_claims(t2)

    section("11", "tools/call refund with the stepped-up token")
    r, _ = mcp("11 refund ok", "tools/call", {"name": "refund", "arguments": {"order_id": "A-1041"}},
               name="refund", token=t2, id=4, brief=call_result)
    check("HTTP 200", r.status_code == 200)

    section("12", "tools/call get_menu with the same stepped-up token (menu:read kept by the union)")
    r, _ = mcp("12 get_menu after step-up", "tools/call", {"name": "get_menu", "arguments": {}}, name="get_menu",
               token=t2, id=5, brief=call_result)
    check("HTTP 200", r.status_code == 200)

    section("13", "Contrast: a client that asks ONLY for the challenged scope (no union)")
    got, verifier = authorize(as_md, client_id, ch2["scope"], RS_URL, issuer, "13 authorize no union")
    r, tok = token_request(as_md, {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
                                   "client_id": client_id, "code_verifier": verifier, "resource": RS_URL},
                           "13 token no union")
    t3 = tok["access_token"]
    show_claims(t3)
    r, _ = mcp("13 get_menu lost", "tools/call", {"name": "get_menu", "arguments": {}}, name="get_menu", token=t3,
               id=6, brief=call_result)
    check("HTTP 403: menu:read is gone", r.status_code == 403)

    section("14", f"Audience: a valid token from the same AS, but issued for another server ({OTHER_RESOURCE})")
    got, verifier = authorize(as_md, client_id, "menu:read", OTHER_RESOURCE, issuer, "14 authorize other resource")
    r, tok = token_request(as_md, {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
                                   "client_id": client_id, "code_verifier": verifier, "resource": OTHER_RESOURCE},
                           "14 token other resource")
    t4 = tok["access_token"]
    show_claims(t4)
    r, _ = mcp("14 wrong audience", "tools/call", {"name": "get_menu", "arguments": {}}, name="get_menu", token=t4,
               id=7, brief=call_result)
    check("HTTP 401 invalid_token", r.status_code == 401
          and www_auth_params(r.headers["www-authenticate"]).get("error") == "invalid_token")

    section("15", "Error responses carry iss too: ask for a scope the AS does not know")
    verifier, challenge = pkce()
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI, "scope": "menu:read admin:all",
         "resource": RS_URL, "code_challenge": challenge, "code_challenge_method": "S256", "state": "s15-demo"}
    r, _ = http("15 invalid_scope", "GET", f"{as_md['authorization_endpoint']}?{urlencode(q)}", brief=lambda b: None)
    got = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    check("iss checked first, == recorded issuer; only then read error", got.get("iss") == issuer)
    out(f"    error={got.get('error')!r} error_description={got.get('error_description')!r}")

    section("16", "Unknown resource: the AS refuses to mint a token for it (RFC 8707 invalid_target)")
    q.update(scope="menu:read", resource="http://127.0.0.1:9999/mcp", state="s16-demo")
    r, _ = http("16 invalid_target", "GET", f"{as_md['authorization_endpoint']}?{urlencode(q)}", brief=lambda b: None)
    got = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    check("iss == recorded issuer", got.get("iss") == issuer)
    out(f"    error={got.get('error')!r} error_description={got.get('error_description')!r}")

    section("17", "Refresh tokens: only when the client asks for offline_access (OIDC style, SEP-2207); rotation")
    got, verifier = authorize(as_md, client_id, "menu:read offline_access", RS_URL, issuer, "17 authorize offline")
    r, tok = token_request(as_md, {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
                                   "client_id": client_id, "code_verifier": verifier, "resource": RS_URL},
                           "17 token offline")
    check("refresh_token issued", bool(tok.get("refresh_token")))
    rt1 = tok["refresh_token"]
    r, tok2 = token_request(as_md, {"grant_type": "refresh_token", "refresh_token": rt1, "client_id": client_id,
                                    "resource": RS_URL}, "17 refresh")
    check("HTTP 200 and a NEW refresh token (rotated)", r.status_code == 200 and tok2["refresh_token"] != rt1)
    r, _ = token_request(as_md, {"grant_type": "refresh_token", "refresh_token": rt1, "client_id": client_id,
                                 "resource": RS_URL}, "17 old refresh refused")
    check("old refresh token refused (invalid_grant)", r.status_code == 400)

    out("")
    out("=== Summary ===")
    for e in exchanges:
        out(f"  {e['step']:<28} {e['request']['method']:<4} {urlparse(e['request']['url']).path:<46} -> {e['response']['status']}")


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    with servers(log_name="raw"):
        try:
            main()
        finally:
            (DATA / "raw_flow.txt").write_text("\n".join(lines) + "\n")
            (DATA / "raw_flow.json").write_text(json.dumps(exchanges, indent=1, ensure_ascii=False) + "\n")
    print(f"\nwrote {DATA / 'raw_flow.txt'} and {DATA / 'raw_flow.json'}")
