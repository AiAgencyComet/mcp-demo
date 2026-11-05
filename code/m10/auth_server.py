"""A small LOCAL authorization server (AS) for the Fernhill demo. Spec 2026-07-28, mcp 2.3.0.

Built from the SDK's AS helpers (create_auth_routes + an OAuthAuthorizationServerProvider), plus the
pieces that 2026-07-28 asks for and the SDK helpers do not add by themselves:
  * `iss` in every authorization response, success and error (RFC 9207, SEP-2468)
  * `authorization_response_iss_parameter_supported: true` in the AS metadata
  * a client may ask for any scope it did not register with (needed for step-up, SEP-2350)
  * RFC 8707: tokens only for known resources; `aud` = the resource
Access tokens are JWTs (ES256). The signing key is made at start-up, lives only in memory, and is thrown away.
Consent is automatic for one made-up person ("barista-ana") so the demo runs with no browser.

Run:  python auth_server.py                     (2026-07-28 behaviour)
      python auth_server.py --sdk-defaults      (only what the SDK helpers give, for comparison)
      python auth_server.py --no-pkce-metadata  (metadata without code_challenge_methods_supported)
      python auth_server.py --narrow-dcr-scopes (metadata lists offline_access, DCR does not accept it)
"""
import secrets
import sys
import time
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, TokenError, construct_redirect_uri)
from mcp.server.auth.routes import build_metadata, create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import ALL_SCOPES, AS_PORT, ISSUER, OTHER_RESOURCE, RS_URL, url  # noqa: E402

SDK_DEFAULTS = "--sdk-defaults" in sys.argv
NO_PKCE_META = "--no-pkce-metadata" in sys.argv
NARROW_DCR = "--narrow-dcr-scopes" in sys.argv   # DCR valid_scopes without offline_access (reproduces a pitfall)
DCR_VALID_SCOPES = ALL_SCOPES if (SDK_DEFAULTS or NARROW_DCR) else ALL_SCOPES + ["offline_access"]
KNOWN_RESOURCES = {RS_URL, OTHER_RESOURCE}
ACCESS_TTL = 600

# Throwaway signing key: made now, kept in memory, gone when the process stops.
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
KID = "m10-" + uuid.uuid4().hex[:8]
PUBLIC_JWK = {**jwt.algorithms.ECAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True),
              "kid": KID, "use": "sig", "alg": "ES256"}


class DemoProvider:
    """In-memory OAuthAuthorizationServerProvider."""

    def __init__(self):
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.refresh: dict[str, RefreshToken] = {}

    async def get_client(self, client_id: str):
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull):
        if not SDK_DEFAULTS:
            # AS policy: a registered client may ASK for any scope this AS knows. What it GETS is decided
            # per request (consent). Without this, the SDK's validate_scope() refuses a step-up request
            # for a scope the client did not name at registration time.
            client_info.scope = " ".join(ALL_SCOPES + ["offline_access"])
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not SDK_DEFAULTS:
            if params.resource is None:
                raise AuthorizeError("invalid_request", "The resource parameter is required (RFC 8707).")
            if params.resource.rstrip("/") not in KNOWN_RESOURCES:
                raise AuthorizeError("invalid_target", f"Unknown resource {params.resource}.")
        # Headless consent: the made-up person "barista-ana" approves the scopes that the client asked for.
        code = secrets.token_urlsafe(32)
        self.codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or ["menu:read"], expires_at=time.time() + 120,
            client_id=client.client_id, code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject="barista-ana")
        extra = {} if SDK_DEFAULTS else {"iss": ISSUER}
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state, **extra)

    async def load_authorization_code(self, client, authorization_code: str):
        return self.codes.get(authorization_code)

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        self.codes.pop(authorization_code.code, None)                     # a code works one time only
        return self._issue(client, authorization_code.scopes, authorization_code.resource,
                           authorization_code.subject)

    async def load_refresh_token(self, client, refresh_token: str):
        return self.refresh.get(refresh_token)

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        self.refresh.pop(refresh_token.token, None)                       # rotate (OAuth 2.1 §4.3.1)
        return self._issue(client, scopes, refresh_token.resource, refresh_token.subject)

    async def load_access_token(self, token: str):
        try:
            c = jwt.decode(token, SIGNING_KEY.public_key(), algorithms=["ES256"], issuer=ISSUER,
                           options={"verify_aud": False})
        except jwt.PyJWTError:
            return None
        return AccessToken(token=token, client_id=c["client_id"], scopes=c["scope"].split(), expires_at=c["exp"],
                           resource=c.get("aud"), subject=c.get("sub"), claims=c)

    async def revoke_token(self, token):
        self.refresh.pop(getattr(token, "token", ""), None)

    def _issue(self, client, scopes: list[str], resource: str | None, subject: str | None) -> OAuthToken:
        if not SDK_DEFAULTS and resource is None:
            raise TokenError("invalid_target", "No resource for this grant.")
        now = int(time.time())
        claims = {"iss": ISSUER, "sub": subject, "aud": resource, "client_id": client.client_id,
                  "scope": " ".join(scopes), "iat": now, "exp": now + ACCESS_TTL, "jti": uuid.uuid4().hex}
        access = jwt.encode(claims, SIGNING_KEY, algorithm="ES256", headers={"kid": KID, "typ": "at+jwt"})
        refresh = None
        if "offline_access" in scopes:                                    # OIDC style: refresh only on request
            refresh = secrets.token_urlsafe(32)
            self.refresh[refresh] = RefreshToken(token=refresh, client_id=client.client_id, scopes=scopes,
                                                 expires_at=now + 86400, resource=resource, subject=subject)
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, scope=" ".join(scopes), refresh_token=refresh)


class IssOnAuthorizationRedirects:
    """Adds `iss` to every 302 from /authorize that does not carry it yet. The SDK's AuthorizationHandler
    builds error redirects (invalid_scope, invalid_target, ...) itself, without `iss`; RFC 9207 §2 wants
    `iss` in error responses too."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_iss(message):
            if message["type"] == "http.response.start" and message["status"] == 302:
                headers = []
                for k, v in message["headers"]:
                    if k.lower() == b"location":
                        u = urlparse(v.decode())
                        q = parse_qsl(u.query)
                        if not any(name == "iss" for name, _ in q):
                            v = urlunparse(u._replace(query=urlencode(q + [("iss", ISSUER)]))).encode()
                    headers.append((k, v))
                message = {**message, "headers": headers}
            await send(message)
        await self.app(scope, receive, send_with_iss)


def metadata_document() -> dict:
    md = build_metadata(url(ISSUER), None,
                        ClientRegistrationOptions(enabled=True, valid_scopes=ALL_SCOPES),
                        RevocationOptions(enabled=False))
    if not SDK_DEFAULTS:
        md.authorization_response_iss_parameter_supported = True               # RFC 9207 §3
        md.scopes_supported = ALL_SCOPES + ["offline_access"]                   # SEP-2207
        md.token_endpoint_auth_methods_supported = ["none", "client_secret_post", "client_secret_basic"]
    doc = md.model_dump(mode="json", exclude_none=True)
    if not SDK_DEFAULTS:
        doc["jwks_uri"] = f"{ISSUER}/jwks"                                     # RFC 8414 field; not in the SDK model
    if NO_PKCE_META:
        doc.pop("code_challenge_methods_supported", None)
    return doc


def build_app() -> Starlette:
    provider = DemoProvider()
    routes = create_auth_routes(provider, url(ISSUER),
                                client_registration_options=ClientRegistrationOptions(enabled=True,
                                                                                      valid_scopes=DCR_VALID_SCOPES))
    doc = metadata_document()

    async def as_metadata(request):
        return JSONResponse(doc, headers={"Cache-Control": "no-store"})

    async def jwks(request):
        return JSONResponse({"keys": [PUBLIC_JWK]})

    out = [Route("/.well-known/oauth-authorization-server", as_metadata, methods=["GET"]),
           Route("/jwks", jwks, methods=["GET"])]
    for r in routes:
        if r.path == "/.well-known/oauth-authorization-server":
            continue                                                            # replaced above
        if r.path == "/authorize" and not SDK_DEFAULTS:
            r.app = IssOnAuthorizationRedirects(r.app)
        out.append(r)
    return Starlette(routes=out)


if __name__ == "__main__":
    mode = "sdk-defaults" if SDK_DEFAULTS else "2026-07-28"
    print(f"AS {ISSUER} mode={mode} no_pkce_metadata={NO_PKCE_META} dcr_valid_scopes={DCR_VALID_SCOPES}", flush=True)
    # access_log=False: the access log would print the /authorize query string (state, code_challenge).
    uvicorn.run(build_app(), host="127.0.0.1", port=AS_PORT, log_level="info", access_log=False)
