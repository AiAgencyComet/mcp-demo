# Module 10 · Login and permissions · RESULTS

Run date 2026-11-04. Python SDK `mcp` 2.3.0 (spec 2026-07-28), `code/.venv-new`, Python 3.12. Everything ran on 127.0.0.1.
All people, clients, orders and keys are made up. The JWT signing key is generated in memory at AS start-up and is never written to disk.
Every token, code, `state`, `code_verifier` and refresh token in these files is cut to its first 8 characters.
No attack was simulated. Every check is our own client against our own local servers, or a pure function call.

## 0. What runs where, and how to re-run

| Part | File | Address |
|---|---|---|
| Authorization server (AS): SDK `create_auth_routes` + an in-memory provider + the 2026-07-28 additions | `code/m10/auth_server.py` | `http://127.0.0.1:9310` |
| Fernhill MCP server = OAuth resource server (RS), per-tool scopes | `code/m10/server.py` (+ `shop.py`, copied from `code/fernhill/`) | `http://127.0.0.1:8310/mcp` |
| Shared config (ports, scope map, redaction, start/stop helper) | `code/m10/common.py` | |
| Raw-HTTP walk-through, 17 steps, no SDK on the client side | `code/m10/demo_raw.py` | → `raw_flow.txt`, `raw_flow.json` |
| SDK client flow (`OAuthClientProvider`, headless browser) | `code/m10/demo_sdk.py` | → `sdk_flow*.txt`, `sdk_flow*.json` |
| Conformance checks: SDK defaults vs spec | `code/m10/checks.py` | → `checks.txt`, `checks.json` |
| Server logs of every run | | `logs/` |
| Copies of the spec pages quoted below | | `spec_snapshot/` |

Scope map (`common.TOOL_SCOPES`): `get_menu`, `order_status` → `menu:read`; `place_order` → `orders:write`; `refund` → `refunds:write`.
The minimal set (PRM `scopes_supported`, and the 401 challenge for non-tool methods) is `menu:read`.
The person who consents is the made-up `barista-ana`. Consent is automatic, so the flow runs with no browser.

```
cd code/m10
../.venv-new/bin/python demo_raw.py                                     # 17 steps, 31 [ok] checks, 0 FAIL
../.venv-new/bin/python demo_sdk.py                                     # SDK flow incl. step-up
../.venv-new/bin/python demo_sdk.py --label sdk_defaults_as  --as-flag=--sdk-defaults
../.venv-new/bin/python demo_sdk.py --label no_pkce_metadata --as-flag=--no-pkce-metadata
../.venv-new/bin/python demo_sdk.py --label narrow_dcr       --as-flag=--narrow-dcr-scopes
../.venv-new/bin/python checks.py
```
Each script starts both servers and stops them in a `finally` (`common.servers`). After the last run, `pgrep -fl "m10/(server|auth_server).py"` printed nothing, and `lsof` shows ports 9310/8310/8311 free.

Server flags (for the comparisons only): `server.py --sdk-defaults` (only the SDK's server-wide `required_scopes=['menu:read']` and SDK challenge headers), `--no-tool-check` (no scope check inside tools).
AS flags: `--sdk-defaults` (only what the SDK helpers give: no `iss`, SDK metadata, the registered scope is kept as sent), `--no-pkce-metadata`, `--narrow-dcr-scopes`.

---

## 1. Verified facts: the 2026-07-28 flow, raw HTTP (`raw_flow.txt`)

**F1. No token → 401 that points to the metadata and names the scope.** Ran `POST /mcp` `tools/list` with no `Authorization`.
```
< 401 Unauthorized
<   www-authenticate: Bearer resource_metadata="http://127.0.0.1:8310/.well-known/oauth-protected-resource/mcp", scope="menu:read"
```
The challenge has no `error` parameter because the request carried no token (RFC 6750 §3.1, Q15). The SDK default sends `error="invalid_token"` here (S2).
Rules: Q2, Q3, Q12a.

**F2. Protected Resource Metadata (RFC 9728) at the path-inserted well-known URI.** `GET /.well-known/oauth-protected-resource/mcp` → 200:
```
{"resource": "http://127.0.0.1:8310/mcp", "authorization_servers": ["http://127.0.0.1:9310"], "scopes_supported": ["menu:read"], "bearer_methods_supported": ["header"], "resource_name": "Fernhill Coffee MCP server"}
```
Exact field names: `resource`, `authorization_servers`, `scopes_supported`, `bearer_methods_supported`. The well-known path is `/.well-known/oauth-protected-resource` + the resource path (`/mcp`), not `/mcp/.well-known/...` (RFC 9728 §3.1, Q17a). The client checked `resource` == the URL it called (RFC 9728 §3.3, Q17b).

**F3. AS metadata (RFC 8414) and the recorded issuer.** `GET http://127.0.0.1:9310/.well-known/oauth-authorization-server` → 200. Key fields:
```
"issuer": "http://127.0.0.1:9310", "code_challenge_methods_supported": ["S256"], "authorization_response_iss_parameter_supported": true,
"scopes_supported": ["menu:read", "orders:write", "refunds:write", "offline_access"], "registration_endpoint": "http://127.0.0.1:9310/register", "jwks_uri": "http://127.0.0.1:9310/jwks"
```
Checks run: `issuer` is identical to the issuer we built the URL from (Q12c), and `S256` is present (Q14c). The suffix is the plain RFC 8414 `oauth-authorization-server`; MCP defines no suffix of its own (Q12b, SEP-2351).

**F4. Dynamic Client Registration with `application_type: "native"`.** `POST /register` → 201. The AS echoed `"application_type": "native", "token_endpoint_auth_method": "none"` (public client, loopback redirect `http://127.0.0.1:9399/callback`). Rule: Q13b (SEP-837). Note: DCR is **deprecated** in 2026-07-28 in favour of Client ID Metadata Documents (Q13a). We use DCR because CIMD needs an https `client_id` URL that the AS fetches (Q13d). CIMD was not run (U1).

**F5. The authorization response carries `iss`, and the client checks it before it uses the code.**
```
<   location: http://127.0.0.1:9399/callback?code=wyUicZkf…&state=qQpVQF7h…&iss=http://127.0.0.1:9310
    [ok] iss is present and == recorded issuer by plain string compare ('http://127.0.0.1:9310')
    [ok] state == the state we sent
```
Rules: Q5a–Q5f, Q16a (SEP-2468).

**F6. The token is bound to the server (`aud` = the `resource`).** The token request sent `resource=http://127.0.0.1:8310/mcp` and `code_verifier`. The token response was `{"access_token": "eyJhbGci…", "token_type": "Bearer", "expires_in": 600, "scope": "menu:read"}` (no refresh token, because none was asked for). Decoded claims:
```
{"iss": "http://127.0.0.1:9310", "sub": "barista-ana", "aud": "http://127.0.0.1:8310/mcp", "client_id": "a8cb9239-…", "scope": "menu:read", "exp": …}
```
Rules: Q6a, Q6b, Q7b.

**F7. One `menu:read` token: discovery and `get_menu` work, `refund` is refused with a step-up challenge.**
`tools/list` → 200 `["get_menu", "place_order", "order_status", "refund"]`. `get_menu` → 200 `structuredContent` with five drinks. Then `refund`:
```
>   Mcp-Method: tools/call
>   Mcp-Name: refund
< 403 Forbidden
<   www-authenticate: Bearer error="insufficient_scope", scope="refunds:write", resource_metadata="http://127.0.0.1:8310/.well-known/oauth-protected-resource/mcp", error_description="The tool refund needs the scope refunds:write"
```
The refusal happens at the HTTP layer, before the tool runs, from the `Mcp-Method`/`Mcp-Name` headers (no body parse). Rules: Q9, Q10a, Q10b, Q15b.

**F8. Step-up with the union of scopes works; without the union the client loses `menu:read`.**
The client asked for `menu:read refunds:write` (old scopes plus challenged scopes). The new token has `"scope": "menu:read refunds:write"`. With it:
`refund` → 200 `"Refunded $5.10 for A-1041 (person: barista-ana, client: a8cb9239)."` and `get_menu` → 200.
Contrast (step 13): a client that asked only for the challenged `refunds:write` got a token that then failed `get_menu`:
```
<   www-authenticate: Bearer error="insufficient_scope", scope="menu:read", ... error_description="The tool get_menu needs the scope menu:read"
```
Rule: Q11a (SEP-2350). The server only names the scope for *this* operation (Q10c), so keeping the old scopes is the client's job.

**F9. A valid token from the same AS, issued for another server, is refused.** A token with `"aud": "http://127.0.0.1:8311/mcp"` was used at Fernhill:
```
< 401 Unauthorized
<   www-authenticate: Bearer error="invalid_token", error_description="The access token is not valid for this server", resource_metadata="...", scope="menu:read"
```
Server log (`logs/raw.server.log`): `fernhill.auth token refused: InvalidAudienceError: Audience doesn't match`. Rules: Q7b, Q7c, Q14e. The SDK's `AuthSettings(validate_token_resource=True)` makes the bearer middleware compare `AccessToken.resource` with `resource_server_url` too; our verifier also passes `audience=RS_URL` to PyJWT.

**F10. Error responses from the AS carry `iss`, and the client checks `iss` before it reads `error`.**
```
<   location: http://127.0.0.1:9399/callback?error=invalid_scope&error_description=Client+was+not+registered+with+scope+admin:all&state=s15-demo&iss=http://127.0.0.1:9310
<   location: http://127.0.0.1:9399/callback?error=invalid_target&error_description=Unknown+resource+http://127.0.0.1:9999/mcp.&state=s16-demo&iss=http://127.0.0.1:9310
```
Rules: Q5b, Q5f, Q16a. `invalid_target` is the RFC 8707 error for an unknown resource.

**F11. Refresh tokens come only when the client asks for `offline_access`; they rotate; the old one is refused.**
Without `offline_access` (F6): no `refresh_token`. With `scope=menu:read offline_access`: `"refresh_token": "OIgddqjH…"`. A refresh → 200 with a new refresh token `"qd2xRFSC…"`. The old one again → `400 {"error": "invalid_grant", "error_description": "refresh token does not exist"}`.
Rules: Q8a–Q8c (SEP-2207), Q14d (rotation for public clients). PRM and the 401/403 challenges do not name `offline_access` (Q8b).

## 2. Verified facts: the SDK client flow (`sdk_flow.txt`)

**F12. `OAuthClientProvider` (mcp 2.3.0) does the whole flow against our AS with no browser, including step-up with the union.**
Order of HTTP requests (verbatim excerpt):
```
sdk  > POST /mcp  method=server/discover            sdk < 401  WWW-Authenticate: Bearer resource_metadata="...", scope="menu:read"
sdk  > GET  /.well-known/oauth-protected-resource/mcp   < 200
sdk  > GET  http://127.0.0.1:9310/.well-known/oauth-authorization-server   < 200
sdk  > POST /register  {"application_type": "native", "scope": "menu:read offline_access", ...}   < 201
browser > GET /authorize  scope='menu:read offline_access' resource='http://127.0.0.1:8310/mcp' code_challenge_method=S256
browser < 302  Location: ...callback?code=4K6y_11w…&state=NbdyVwcg…&iss=http://127.0.0.1:9310
sdk  > POST /token  {"grant_type": "authorization_code", "code": "4K6y_11w…", "code_verifier": "wQfJ_Fep…", "resource": "http://127.0.0.1:8310/mcp"}   < 200
sdk  > POST /mcp  method=server/discover  [Authorization: Bearer eyJhbGci…]   < 200
... tools/list 200, get_menu 200 ...
sdk  > POST /mcp  method=tools/call name=refund      sdk < 403  WWW-Authenticate: Bearer error="insufficient_scope", scope="refunds:write", ...
browser > GET /authorize  scope='menu:read offline_access refunds:write' ...
sdk  > POST /token ... < 200
sdk  > POST /mcp  method=tools/call name=refund   < 200   "Refunded $7.50 for A-1042 (person: barista-ana, client: ...)"
```
Measured: 12 SDK HTTP requests and 2 browser legs for connect, list, get_menu, refund (with step-up), get_menu. The first connection costs 6 SDK requests + 1 browser leg before the first MCP result. The step-up costs 3 SDK requests + 1 browser leg, and the SDK does not fetch the metadata again.
Final stored token: `scope='menu:read offline_access refunds:write'`. Stored registration: `{"application_type": "native", "issuer_binding": "http://127.0.0.1:9310", ...}`.
What this shows about SDK 2.3.0:
- The first MCP request of `Client(..., mode="auto")` is `server/discover`, so that is where the first 401 lands.
- The client **adds `offline_access` by itself** when the AS lists it in `scopes_supported` and the client's `grant_types` includes `refresh_token` (code: `get_client_metadata_scopes`, comment "SEP-2207"). Our server did not ask for it.
- Step-up = `403` + `error="insufficient_scope"` → union of old and challenged scopes (`union_scopes`, comment "SEP-2350").
- `iss` is checked against the metadata issuer (`validate_authorization_response_iss`, "RFC 9207"), and the registration is stamped with the issuer (`OAuthClientInformationFull.issuer`, "SEP-2352").
- DCR sends `application_type: "native"` by default (`OAuthClientMetadata.application_type` default, "SEP-837").

**F13. A tool can read the verified token.** `mcp.server.auth.middleware.auth_context.get_access_token()` returns the `AccessToken` inside a tool on 2026-07-28 Streamable HTTP. Log line: `fernhill.auth tool sees token via get_access_token(): sub=barista-ana scopes=['menu:read', 'offline_access', 'refunds:write']`. The refund result uses `tok.subject` and `tok.client_id`.

## 3. SDK 2.3.0 vs the spec: what you must add yourself (each with a run)

**S1. `required_scopes` is one list for the whole server: no per-tool scopes.** (`checks.txt` A4) With `--sdk-defaults --no-tool-check`, a `menu:read`-only token called `refund`:
`< 200 ... result isError=False text='Refunded $5.10 for A-1041 (person: barista-ana, client: 806ad35b).'`
The PRM route also takes `scopes_supported` from the same `required_scopes` (code: `create_protected_resource_routes(..., scopes_supported=auth.required_scopes)`). Our fix: `ToolScopeGate` in `server.py`, an ASGI middleware appended after the SDK's `AuthenticationMiddleware`, and a replaced PRM route.

**S2. The SDK's 401 sends `error="invalid_token"` even when no token was sent, and gives no `scope`.** (A1 and A2 give identical headers)
```
< 401  WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="http://127.0.0.1:8310/.well-known/oauth-protected-resource/mcp"
```
RFC 6750 §3.1 says SHOULD NOT include an error code when the request has no authentication (Q15a). MCP says SHOULD include `scope` (Q3).

**S3. The SDK's 403 has no `scope` parameter.** (A3, `refunds:write`-only token on `tools/list`)
```
< 403  WWW-Authenticate: Bearer error="insufficient_scope", error_description="Required scope: menu:read", resource_metadata="..."
```
The needed scope is only in the human text. The spec's 403 shape has `scope="..."` (Q10a). What the SDK client does with a 403 that has no `scope` was not run (U4).

**S4. A scope check inside the tool cannot trigger step-up.** (A5, `--sdk-defaults` with our in-tool check)
`< 200 WWW-Authenticate: None ... result isError=True text='Error executing tool refund: This token does not have the scope refunds:write.'`
The OAuth layer of the client only reacts to HTTP 401/403. A tool error is HTTP 200, so the client never re-authorizes. The scope decision must be made at the HTTP layer. The 2026-07-28 `Mcp-Method`/`Mcp-Name` headers let you do that without parsing the body. We keep the in-tool check only as a second layer.

**S5. The SDK AS helpers add no `iss` and no `authorization_response_iss_parameter_supported`.** (`checks.txt` B)
`flags=--sdk-defaults: {"authorization_response_iss_parameter_supported": "(absent)", "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"], "jwks_uri": "(absent)", ...}`
`SDK-defaults AS ... authorization response params: ['code', 'state']  (iss present: False)`.
The SDK's `AuthorizationHandler` also builds error redirects itself, with no `iss` (model `AuthorizationErrorResponse` has no `iss` field). Our AS adds `iss` in the provider's `authorize()` (success) and in an ASGI wrapper on `/authorize` (errors), sets the flag, adds `"none"` to the auth methods, and adds `jwks_uri` (the SDK `OAuthMetadata` model has no `jwks_uri` field, so we serve a dict). Against the SDK-defaults AS, the SDK client accepted the response with no `iss` (row 4 of the table, correct per Q5c).

**S6. SDK client + SDK AS helpers, out of the box: step-up fails.** (`sdk_flow_sdk_defaults_as.txt`)
```
browser > GET /authorize  scope='menu:read refunds:write' ...
browser < 302  Location: ...callback?error=invalid_scope&error_description=Client+was+not+registered+with+scope+refunds:write&state=-uvPVG3S…
EXCEPTION (connect/flow): OAuthFlowError: No authorization code received
stored client registration: {..., "registered_scope": "menu:read"}
```
Cause: the SDK client registers with the scope of the first challenge. The SDK AS stores it as the client's allowed scope, and `OAuthClientInformationFull.validate_scope()` then refuses any scope outside it, including the step-up union. Our fix (`DemoProvider.register_client`): the AS lets a registered client *ask* for any scope it knows, and consent decides what it *gets*. Also: `AuthorizationCodeResult` has no `error` field, so the SDK error text says only "No authorization code received". Your `callback_handler` must show the AS error itself.

**S7. SDK AS: a client that registers without `scope` cannot get any scope** unless `ClientRegistrationOptions.default_scopes` is set. (`checks.txt` B)
`registered scope=None ... authorize scope=menu:read -> error='invalid_scope' error_description='Client was not registered with scope menu:read'`

**S8. If the AS metadata lists `offline_access`, the DCR handler must accept it.** (`sdk_flow_narrow_dcr.txt`) The SDK client added `offline_access` (F12), and the SDK `RegistrationHandler` checks requested scopes against `valid_scopes`:
`OAuthRegistrationError: Registration failed: 400 {"error":"invalid_client_metadata","error_description":"Requested scopes are not valid: offline_access"}`
This was a bug in our own first build of the AS. It is a likely mistake in real setups.

**S9. The SDK client does not refuse an AS whose metadata has no `code_challenge_methods_supported`.** (`sdk_flow_no_pkce_metadata.txt`; `checks.txt` B shows `"code_challenge_methods_supported": "(absent)"` for that flag)
The client went on: `browser > GET /authorize ... code_challenge_method=S256` → 302 with a code → tokens → refund OK. The spec says the client MUST refuse to proceed (Q14c). Code: no reference to `code_challenge_methods_supported` anywhere in `mcp/client/` (grep, 0 hits). This is a deviation in SDK 2.3.0. Impact is low when the AS supports PKCE anyway, but the MUST is not enforced.

**S10. The SDK token endpoint ignores the token-request `resource`.** (`checks.txt` E) The authorize request had `resource=http://127.0.0.1:8310/mcp` and the token request `resource=http://127.0.0.1:8311/mcp`. Result: `token endpoint HTTP 200, issued token aud='http://127.0.0.1:8310/mcp'`. `TokenHandler` parses `resource` but does not pass it to `exchange_authorization_code`, so the token keeps the resource from the code. That is safe (no widening), but an AS cannot answer `invalid_target` for a mismatch without its own handler. Clients still MUST send it in both requests (Q6b).

**S11. Pitfall: pydantic `AnyHttpUrl` adds a trailing slash to a path-less issuer.** (`checks.txt` D)
`str(AnyHttpUrl('http://127.0.0.1:9310')) -> 'http://127.0.0.1:9310/'`, while `TypeAdapter(AnyHttpUrl, config=ConfigDict(url_preserve_empty_path=True))` gives `'http://127.0.0.1:9310'`. Our first AS build served `"issuer": "http://127.0.0.1:9310/"` while `iss` was `http://127.0.0.1:9310`. The comparison is exact (Q5e), so the SDK client rejects it. Table row 5: `iss=http://127.0.0.1:9310/ ... SDK: reject (Authorization response iss mismatch: http://127.0.0.1:9310/ != http://127.0.0.1:9310)`. Pass URLs to `AuthSettings` as strings (its config keeps the empty path), or use the adapter (`common.url()`).

**S12. The SDK's `iss` check matches the spec table.** (`checks.txt` C, pure function `validate_authorization_response_iss`, 6 rows, all agree with the spec)
```
flag=true   iss=http://127.0.0.1:9310   spec: proceed   SDK: proceed
flag=true   iss=None                    spec: reject    SDK: reject (Authorization response missing iss parameter advertised by the authorization server)
flag=absent iss=http://127.0.0.1:9310   spec: proceed   SDK: proceed
flag=absent iss=None                    spec: proceed   SDK: proceed
flag=true   iss=http://127.0.0.1:9310/  spec: reject (no normalization)   SDK: reject
flag=true   iss=http://localhost:9310   spec: reject    SDK: reject
```

**S13. The SDK client parses our challenge correctly.** (`checks.txt` F) `{"error": "insufficient_scope", "scope": "refunds:write", "resource_metadata": "http://127.0.0.1:8310/.well-known/oauth-protected-resource/mcp"}`.

## 4. What tutorials get wrong or do not cover

1. **A bare 401 is not enough.** The 401 must carry `resource_metadata` (or the server must serve the well-known URI), and SHOULD carry `scope`. With no token, send no `error` code (F1, S2, Q3, Q12a, Q15a).
2. **The well-known path is inserted before the path:** `/.well-known/oauth-protected-resource/mcp`, not `/mcp/.well-known/...` (F2, Q17a). The AS suffix is the plain RFC 8414 one (Q12b).
3. **PRM `scopes_supported` is the *minimal* set, not every scope.** A client with no challenge `scope` requests all of `scopes_supported` (Q4). Listing every scope there makes clients ask for too much. (RFC 9728 only says "scope values ... used in authorization requests", Q17c. The "minimal set" intent is MCP's own.)
4. **Per-tool scopes are not built in** (S1). The decision must be an HTTP 403 with `error="insufficient_scope"` and `scope`, not a tool error, or step-up cannot happen (S4).
5. **Step-up = union.** The server names only what this operation needs. The client keeps what it had (F8, Q10c, Q11a). The client SHOULD also limit retries (Q11c).
6. **Check `iss` before you send the code anywhere, on errors too, with exact string compare** (F5, F10, S11, S12, Q5).
7. **`resource` in both requests, `aud` check at the server, no token passthrough** (F6, F9, Q6, Q7, Q14e).
8. **DCR is deprecated in 2026-07-28. CIMD is the default for "no prior relationship"**, and DCR clients MUST send `application_type` (`native` for desktop/CLI/localhost) (F4, Q13).
9. **Refresh tokens:** ask with `offline_access` only when the AS lists it. Never put it in PRM or challenges. Expect none. Rotation is a MUST for public clients (F11, Q8, Q14d).
10. **PKCE support must be verified from AS metadata, and `S256` must be used** (F3, S9, Q14c).
11. **stdio servers SHOULD NOT use this flow.** They take credentials from the environment (Q1).
12. **The `Authorization` header goes on every HTTP request.** Tokens never go in the query string (Q7a).
13. **AS endpoints MUST be HTTPS. Redirect URIs MUST be localhost or HTTPS** (Q14a). Our http AS is a loopback-only exception that the SDK allows "for testing" (Q19). RFC 9207 itself says `iss` MUST be an https URL (Q16b). Say this on screen.
14. **Credentials are bound to the issuer.** Re-register when the PRM names a different AS (Q13c, SEP-2352). Code read only, not run (U5).

## 5. Design notes (not runs)

- **Why the scope gate can trust `Mcp-Name`.** The gate reads the 2026-07-28 headers, not the body. This is safe only because the 2026-07-28 transport refuses a request whose header disagrees with the body (verified in module 3, DESIGN.md §7: `-32020` "mcp-name header does not match the request body's 'name' parameter", HTTP 400). Per the course rule (no attack demos), we did not run a header/body mismatch against the gate. The scope check inside each tool (`need()`) is the second layer.
- **`tools/list` shows all four tools to any valid token.** That is a choice. Hiding tools by scope would stop the model from calling `refund` at all, so the client would never get the 403 that starts step-up.
- **Scope hierarchy:** the spec says servers MUST account for broader scopes that imply narrower ones (Q11b). Our three scopes are flat, so nothing implies anything.
- **The refund tool here has no confirm step** (module 7 has it), to keep this module on scopes. Module 11 can show both defenses side by side: scopes (this module) and confirm (module 7).
- **Mix-up attacks (concept only, for module 11 narration; nothing was simulated).** One client talks to many servers, and each server can name its own AS. If one AS is hostile, it can try to make the client send it a code that an honest AS issued, for example by answering a flow that the client started with the honest AS (Q14b; RFC 9207 §1). The defense is cheap. The client records the issuer it chose when it starts the flow, and the AS puts `iss` in its response. The client compares them as plain strings before it sends the code to any token endpoint. On mismatch it stops and does not show the error text (Q5).

## 6. UNCONFIRMED / not covered here

- **U1** Client ID Metadata Documents (CIMD): not run. It needs an https `client_id` URL that the AS fetches. The SDK supports it via `OAuthClientProvider(client_metadata_url=...)` and AS `client_id_metadata_document_supported` (code read only).
- **U2** OIDC discovery (`/.well-known/openid-configuration`): not run. Our AS serves only RFC 8414 metadata. The SDK builds the fallback URL list (`build_oauth_authorization_server_metadata_discovery_urls`, code read).
- **U3** Real hosts (Claude Desktop, Claude Code, VS Code) connecting to this OAuth server: not run.
- **U4** SDK client behaviour on a 403 `insufficient_scope` with no `scope` parameter (the SDK server's own 403), and its retry limit on repeated step-ups: not run.
- **U5** SEP-2352 re-registration when the AS changes: code read only (`credentials_match_issuer`), not run.
- **U6** Automatic refresh by the SDK client when the access token expires (our tokens live 600 s; the runs were shorter): not run. Raw refresh with rotation was run (F11).
- **U7** Timing: the runs are local, so timing numbers mean nothing and were not taken. Request counts are in F12.

## 7. Spec and RFC quotes used above (verbatim; copies in `spec_snapshot/`)

Main page: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- **Q1** "Implementations using an STDIO transport **SHOULD NOT** follow this specification, and instead retrieve credentials from the environment."
- **Q2** "MCP servers **MUST** implement OAuth 2.0 Protected Resource Metadata ([RFC9728]). MCP clients **MUST** use OAuth 2.0 Protected Resource Metadata for [authorization server discovery]."
- **Q3** "MCP servers **SHOULD** include a `scope` parameter in the `WWW-Authenticate` header as defined in [RFC 6750 Section 3] to indicate the scopes required for accessing the resource."
- **Q4** "**If `scope` is not available**, use all scopes defined in `scopes_supported` from the Protected Resource Metadata document" and "The `scopes_supported` field is intended to represent the minimal set of scopes necessary for basic functionality ..., with additional scopes requested incrementally through the step-up authorization flow steps"
- **Q5a** "Before redirecting the user-agent, the client **MUST** record the `issuer` value from the selected authorization server's validated metadata document"
- **Q5b** "MCP authorization servers **SHOULD** include the `iss` parameter in authorization responses, including error responses, as defined in [RFC9207 Section 2]. Authorization servers that include the `iss` parameter **MUST** advertise this by setting `authorization_response_iss_parameter_supported` to `true` in their metadata"
- **Q5c** Table: `true`/present → compare; `true`/absent → "Reject the response"; `false or absent`/present → compare; `false or absent`/absent → "Proceed".
- **Q5d** "On receiving the authorization response, MCP clients **MUST** apply the validation in [RFC9207 Section 2.4] before transmitting the authorization code to any token endpoint"
- **Q5e** "clients **MUST NOT** apply scheme or host case folding, default-port elision, trailing-slash, or percent-encoding normalization ... before comparison."
- **Q5f** "This validation applies equally to error responses - on mismatch the client **MUST NOT** act on or display `error`, `error_description`, or `error_uri`."
- **Q6a** "MCP clients **MUST** implement Resource Indicators for OAuth 2.0 as defined in [RFC 8707]"; **Q6b** "**MUST** be included in both authorization requests and token requests."
- **Q7a** "Note that authorization **MUST** be included in every HTTP request from client to server." / "Access tokens **MUST NOT** be included in the URI query string"
- **Q7b** "MCP servers **MUST** validate that access tokens were issued specifically for them as the intended audience"; **Q7c** "Invalid or expired tokens **MUST** receive a HTTP 401 response."
- **Q8a** "**MAY** add `offline_access` to the `scope` parameter of the authorization and token requests when the Authorization Server metadata contains it in `scopes_supported`"; **Q8b** "**MCP Servers** (Protected Resources) **SHOULD NOT** include `offline_access` in `WWW-Authenticate` scope or Protected Resource Metadata `scopes_supported`"; **Q8c** "**MUST NOT** assume refresh tokens will be issued; the AS retains discretion"
- **Q9** Error table: "401 | Unauthorized | Authorization required or token invalid"; "403 | Forbidden | Invalid scopes or insufficient permissions"; "400 | Bad Request | Malformed authorization request"
- **Q10a** Runtime insufficient scope: "`HTTP 403 Forbidden` status code" with "`error="insufficient_scope"`", "`scope="required_scope1 required_scope2"`", "`resource_metadata`", "`error_description` (optional)"
- **Q10b** "servers **SHOULD** include all scopes required for the current operation in a single challenge."
- **Q10c** "servers are not required to include the client's previously granted scopes." / "Scope accumulation across operations is a client-side responsibility."
- **Q11a** "**Determine required scopes** by computing the union of the client's previously requested scope set and the scopes from the current challenge."
- **Q11b** "Servers **MUST** account for scope hierarchies, where a broader scope implies narrower ones"; **Q11c** "Clients **SHOULD** implement retry limits"

Discovery: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery
- **Q12a** "Include the resource metadata URL in the `WWW-Authenticate` HTTP header under `resource_metadata` when returning `401 Unauthorized` responses" (one of two allowed mechanisms; the other is the well-known URI; clients MUST support both).
- **Q12b** "MCP uses the default `oauth-authorization-server` well-known URI suffix defined in [RFC 8414 Section 3.1] ... MCP does not define an application-specific well-known URI suffix."
- **Q12c** "the `issuer` value in the document **MUST** be identical to the issuer identifier used to construct the well-known URL. If they differ, the client **MUST NOT** use the metadata."

Client registration: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration
- **Q13a** "Dynamic Client Registration is deprecated. New implementations should use [Client ID Metadata Documents] instead."
- **Q13b** "MCP clients **MUST** specify an appropriate `application_type` during Dynamic Client Registration." / "**Native applications** (desktop applications, mobile apps, CLI tools, and locally-hosted web applications accessed via `localhost`) **SHOULD** use `application_type: "native"`"
- **Q13c** "**MUST** associate those credentials with the specific authorization server that issued them, keyed by the authorization server's `issuer` identifier."
- **Q13d** "The `client_id` URL **MUST** use the "https" scheme and contain a path component"

Security considerations: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations
- **Q14a** "All authorization server endpoints **MUST** be served over HTTPS." / "All redirect URIs **MUST** be either `localhost` or use HTTPS."
- **Q14b** "An attacker that controls one of the authorization servers an MCP client interacts with may attempt to have the client send it an authorization code or token issued by a different, honest authorization server (a mix-up attack ...)."
- **Q14c** "If `code_challenge_methods_supported` is absent, the authorization server does not support PKCE and MCP clients **MUST** refuse to proceed." / "MCP clients **MUST** use the `S256` code challenge method when technically capable"
- **Q14d** "For public clients, authorization servers **MUST** rotate refresh tokens"
- **Q14e** "The MCP server **MUST NOT** pass through the token it received from the MCP client."

RFCs:
- **Q15a** RFC 6750 §3.1 (https://www.rfc-editor.org/rfc/rfc6750#section-3.1): "If the request lacks any authentication information ..., the resource server SHOULD NOT include an error code or other error information."
- **Q15b** RFC 6750 §3.1: "insufficient_scope: The request requires higher privileges than provided by the access token. The resource server SHOULD respond with the HTTP 403 (Forbidden) status code and MAY include the "scope" attribute with the scope necessary to access the protected resource."
- **Q16a** RFC 9207 §2 (https://www.rfc-editor.org/rfc/rfc9207#section-2): "In authorization responses to the client, including error responses, an authorization server supporting this specification MUST indicate its identity by including the iss parameter in the response."
- **Q16b** RFC 9207 §2: "Its value MUST be a URL that uses the "https" scheme without any query or fragment components."
- **Q17a** RFC 9728 §3.1 (https://www.rfc-editor.org/rfc/rfc9728#section-3.1): "any terminating slash (/) following the host component MUST be removed before inserting /.well-known/ and the well-known URI path suffix between the host component and the path and/or query components."
- **Q17b** RFC 9728 §3.3: "The resource value returned MUST be identical to the protected resource's resource identifier value into which the well-known URI path suffix was inserted to create the URL used to retrieve the metadata."
- **Q17c** RFC 9728 §2: "scopes_supported RECOMMENDED. JSON array containing a list of scope values ... that are used in authorization requests to request access to this protected resource."

Release post (https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/, "Authorization Hardening"):
- **Q18** "Clients must now validate the iss parameter on authorization responses per RFC 9207 (SEP-2468)." / "Clients now declare their OpenID Connect application_type during Dynamic Client Registration (SEP-837), avoiding the common case where an authorization server defaults a desktop or CLI client to "web" and rejects its localhost redirect URI." / "Clients bind registered credentials to the issuing authorization server's issuer and re-register when a resource migrates between authorization servers (SEP-2352)." / "how to request refresh tokens from OpenID Connect-style authorization servers (SEP-2207), and clarifies scope accumulation during step-up (SEP-2350) and the .well-known discovery suffix (SEP-2351)."

SDK source (mcp 2.3.0):
- **Q19** `mcp/server/auth/routes.py` `validate_issuer_url`: "# RFC 8414 requires HTTPS, but we allow loopback/localhost HTTP for testing"

## Added 2026-11-05 · source for "MCP uses OAuth 2.1" (script/m10.md)
spec_snapshot/authorization.md (https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), line 48:
"A protected *MCP server* acts as an OAuth 2.1 resource server"; line 61: "Authorization servers **MUST** implement OAuth 2.1 with appropriate security ...".
