"""Module 10 conformance checks: what the SDK gives out of the box vs what the 2026-07-28 spec asks for.
No attack simulation: every check is our own client talking to our own local servers, or a pure function call.
Writes data/m10/checks.txt and data/m10/checks.json."""
import base64
import hashlib
import json
import secrets
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import (DATA, HERE, ISSUER, META, OTHER_RESOURCE, PV, PY, REDIRECT_URI, RS_URL, jwt_claims,  # noqa: E402
                    servers)

lines: list[str] = []
results: dict = {}
http = httpx.Client(timeout=20, follow_redirects=False)


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def mcp(method: str, params=None, name=None, token=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": PV, "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    if token:
        h["Authorization"] = f"Bearer {token}"
    return http.post(RS_URL, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method,
                                               "params": {**(params or {}), "_meta": META}})


def body_text(r):
    ct = r.headers.get("content-type", "")
    if "event-stream" in ct:
        d = [ln[5:].strip() for ln in r.text.splitlines() if ln.startswith("data:")]
        return json.loads(d[-1]) if d else r.text
    try:
        return r.json()
    except ValueError:
        return r.text


class Tokens:
    """Quiet helper: register once, then authorization code + PKCE for any scope/resource."""

    def __init__(self, reg_scope: str | None = None):
        self.md = http.get(f"{ISSUER}/.well-known/oauth-authorization-server").json()
        body = {"client_name": "m10 checks", "redirect_uris": [REDIRECT_URI], "application_type": "native",
                "grant_types": ["authorization_code"], "response_types": ["code"], "token_endpoint_auth_method": "none"}
        if reg_scope:
            body["scope"] = reg_scope
        reg = http.post(self.md["registration_endpoint"], json=body)
        self.client_id = reg.json()["client_id"]
        self.registered_scope = reg.json().get("scope")

    def authorize(self, scope: str, resource: str):
        v = secrets.token_urlsafe(64)
        ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": REDIRECT_URI, "scope": scope,
             "resource": resource, "code_challenge": ch, "code_challenge_method": "S256", "state": "chk"}
        r = http.get(f"{self.md['authorization_endpoint']}?{urlencode(q)}")
        return {k: v2[0] for k, v2 in parse_qs(urlparse(r.headers["location"]).query).items()}, v

    def token(self, scope: str, resource: str = RS_URL, token_resource: str | None = None) -> dict:
        got, v = self.authorize(scope, resource)
        r = http.post(self.md["token_endpoint"], data={
            "grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI,
            "client_id": self.client_id, "code_verifier": v, "resource": token_resource or resource})
        return {"status": r.status_code, **r.json()}


def show(label: str, r: httpx.Response) -> dict:
    rec = {"status": r.status_code, "www-authenticate": r.headers.get("www-authenticate"), "body": body_text(r)}
    out(f"  {label}")
    out(f"    < {r.status_code}  WWW-Authenticate: {rec['www-authenticate']}")
    b = rec["body"]
    if isinstance(b, dict) and "result" in b:
        res = b["result"]
        txt = " ".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        out(f"    < result isError={res.get('isError', False)} text={txt[:100]!r}")
    else:
        out(f"    < body {json.dumps(b)[:160]}")
    return rec


def section(title: str) -> None:
    out("")
    out(f"=== {title} ===")


def check_a_sdk_default_rs():
    section("A. Resource server with SDK defaults only (required_scopes=['menu:read'] for the whole server)")
    rec = {}
    refund = {"name": "refund", "arguments": {"order_id": "A-1041"}}
    with servers(rs_flags=("--sdk-defaults", "--no-tool-check"), log_name="checks_A"):
        prm = http.get("http://127.0.0.1:8310/.well-known/oauth-protected-resource/mcp").json()
        out(f"  PRM: {json.dumps(prm)}")
        rec["prm"] = prm
        rec["no_token"] = show("A1 tools/list, no Authorization header", mcp("tools/list"))
        rec["bad_token"] = show("A2 tools/list, Authorization: Bearer not-a-real-token",
                                mcp("tools/list", token="not-a-real-token"))
        t = Tokens()
        only_refunds = t.token("refunds:write")["access_token"]
        menu = t.token("menu:read")["access_token"]
        rec["wrong_scope"] = show("A3 tools/list with a refunds:write-only token",
                                  mcp("tools/list", token=only_refunds))
        rec["menu_token_refund_sdk_only"] = show(
            "A4 tools/call refund with a menu:read-only token; SDK server-wide scope only, no in-tool check",
            mcp("tools/call", refund, name="refund", token=menu))
    with servers(rs_flags=("--sdk-defaults",), log_name="checks_A5"):
        t = Tokens()
        menu = t.token("menu:read")["access_token"]
        rec["menu_token_refund_tool_check"] = show(
            "A5 the same call; SDK server-wide scope + a scope check INSIDE the tool (no HTTP 403, so no step-up)",
            mcp("tools/call", refund, name="refund", token=menu))
    results["A_sdk_default_rs"] = rec


def check_b_as_metadata():
    section("B. AS metadata: SDK helper defaults vs this module's AS")
    rec = {}
    for flag in ("--sdk-defaults", "", "--no-pkce-metadata"):
        doc = json.loads(subprocess.run([PY, "-c", "import sys,json; sys.argv=['x', %r]; import auth_server;"
                                         "print(json.dumps(auth_server.metadata_document()))" % flag],
                                        capture_output=True, text=True, cwd=HERE, check=True).stdout)
        keys = {k: doc.get(k, "(absent)") for k in ("issuer", "authorization_response_iss_parameter_supported",
                                                     "code_challenge_methods_supported", "scopes_supported",
                                                     "token_endpoint_auth_methods_supported", "jwks_uri")}
        out(f"  flags={flag or '(none)'}: {json.dumps(keys)}")
        rec[flag or "default"] = doc
    with servers(as_flags=("--sdk-defaults",), log_name="checks_B"):
        t = Tokens(reg_scope="menu:read")
        got, _ = t.authorize("menu:read", RS_URL)
        out(f"  SDK-defaults AS, client registered with scope 'menu:read', authorize scope=menu:read:")
        out(f"    authorization response params: {sorted(got)}  (iss present: {'iss' in got})")
        rec["sdk_defaults_authorize_params"] = sorted(got)
        t2 = Tokens()
        got2, _ = t2.authorize("menu:read", RS_URL)
        out(f"  SDK-defaults AS, client registered WITHOUT a scope field (registered scope={t2.registered_scope!r}):")
        out(f"    authorize scope=menu:read -> error={got2.get('error')!r} "
            f"error_description={got2.get('error_description')!r}")
        rec["sdk_defaults_no_reg_scope"] = {"registered_scope": t2.registered_scope, "error": got2.get("error"),
                                            "error_description": got2.get("error_description")}
    results["B_as_metadata"] = rec


def check_c_rfc9207_table():
    section("C. RFC 9207 table (MCP 2026-07-28) vs the SDK's validate_authorization_response_iss (pure function)")
    from mcp.client.auth.exceptions import OAuthFlowError
    from mcp.client.auth.utils import validate_authorization_response_iss
    from mcp.shared.auth import OAuthMetadata
    base = {"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token"}
    rows = [
        ("true", ISSUER, "compare: equal -> proceed"),
        ("true", None, "reject"),
        ("absent", ISSUER, "compare: equal -> proceed"),
        ("absent", None, "proceed"),
        ("true", ISSUER + "/", "compare: differs by a trailing slash -> reject (no normalization)"),
        ("true", ISSUER.replace("127.0.0.1", "localhost"), "compare: other host string -> reject"),
    ]
    rec = []
    for flag, iss, spec_says in rows:
        md = OAuthMetadata(**base, **({"authorization_response_iss_parameter_supported": True} if flag == "true" else {}))
        try:
            validate_authorization_response_iss(iss, md)
            sdk = "proceed"
        except OAuthFlowError as e:
            sdk = f"reject ({e})"
        out(f"  flag={flag:<6} iss={str(iss):<28} spec: {spec_says:<62} SDK: {sdk}")
        rec.append({"flag": flag, "iss": iss, "spec": spec_says, "sdk": sdk})
    results["C_rfc9207_table"] = rec


def check_d_trailing_slash():
    section("D. Pitfall: pydantic AnyHttpUrl adds a trailing slash to a path-less issuer")
    from pydantic import AnyHttpUrl
    from common import url
    a, b = str(AnyHttpUrl(ISSUER)), str(url(ISSUER))
    out(f"  str(AnyHttpUrl({ISSUER!r}))                       -> {a!r}")
    out(f"  str(TypeAdapter(AnyHttpUrl, url_preserve_empty_path=True)) -> {b!r}")
    out(f"  equal as strings: {a == b}")
    results["D_trailing_slash"] = {"AnyHttpUrl": a, "preserve_empty_path": b}


def check_e_token_resource():
    section("E. SDK TokenHandler and the token-request `resource` (RFC 8707 says send it in both requests)")
    with servers(log_name="checks_E"):
        t = Tokens()
        r = t.token("menu:read", resource=RS_URL, token_resource=OTHER_RESOURCE)
        aud = jwt_claims(r["access_token"])["aud"] if r.get("access_token") else None
        out(f"  authorize resource={RS_URL}  token request resource={OTHER_RESOURCE}")
        out(f"  -> token endpoint HTTP {r['status']}, issued token aud={aud!r} (the token-request value is not consulted)")
        results["E_token_resource"] = {"status": r["status"], "aud": aud, "token_request_resource": OTHER_RESOURCE}


def check_f_sdk_challenge_parse():
    section("F. The SDK client's WWW-Authenticate parser on this server's 403 challenge")
    from mcp.client.auth.utils import extract_field_from_www_auth, extract_resource_metadata_from_www_auth
    hv = ('Bearer error="insufficient_scope", scope="refunds:write", resource_metadata="http://127.0.0.1:8310/'
          '.well-known/oauth-protected-resource/mcp", error_description="The tool refund needs the scope refunds:write"')
    resp = httpx.Response(403, headers={"www-authenticate": hv})
    got = {"error": extract_field_from_www_auth(resp, "error"), "scope": extract_field_from_www_auth(resp, "scope"),
           "resource_metadata": extract_resource_metadata_from_www_auth(resp)}
    out(f"  parsed: {json.dumps(got)}")
    results["F_parse"] = got


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    out("MCP masterclass · module 10 · conformance checks (mcp 2.3.0, spec 2026-07-28); tokens never printed")
    try:
        check_a_sdk_default_rs()
        check_b_as_metadata()
        check_c_rfc9207_table()
        check_d_trailing_slash()
        check_e_token_resource()
        check_f_sdk_challenge_parse()
    finally:
        (DATA / "checks.txt").write_text("\n".join(lines) + "\n")
        (DATA / "checks.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str) + "\n")
    print(f"\nwrote {DATA / 'checks.txt'}")
