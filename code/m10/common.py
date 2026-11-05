"""Module 10 shared settings: ports, scopes, redaction, and a helper that starts and stops the two servers.
Everything runs on 127.0.0.1. All users, clients and keys are made up and live only in memory."""
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import AnyHttpUrl, ConfigDict, TypeAdapter

HERE = Path(__file__).resolve().parent
DATA = HERE.parent.parent / "data" / "m10"
PY = sys.executable

AS_PORT, RS_PORT, OTHER_PORT = 9310, 8310, 8311
ISSUER = f"http://127.0.0.1:{AS_PORT}"                    # the authorization server (AS)
RS_URL = f"http://127.0.0.1:{RS_PORT}/mcp"                 # canonical URI of the Fernhill MCP server
PRM_URL = f"http://127.0.0.1:{RS_PORT}/.well-known/oauth-protected-resource/mcp"
OTHER_RESOURCE = f"http://127.0.0.1:{OTHER_PORT}/mcp"      # a second made-up server (never started)
REDIRECT_URI = "http://127.0.0.1:9399/callback"            # the client's loopback callback (nothing listens)

# One scope per kind of action. The server checks these per tool.
TOOL_SCOPES = {
    "get_menu": ["menu:read"],
    "order_status": ["menu:read"],
    "place_order": ["orders:write"],
    "refund": ["refunds:write"],
}
BASE_SCOPES = ["menu:read"]                                # the minimal set (PRM scopes_supported)
ALL_SCOPES = ["menu:read", "orders:write", "refunds:write"]

PV = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": PV,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "m10-raw", "version": "1"}}


_URL = TypeAdapter(AnyHttpUrl, config=ConfigDict(url_preserve_empty_path=True))


def url(value: str) -> AnyHttpUrl:
    """AnyHttpUrl that keeps a path-less URL as written. Plain AnyHttpUrl("http://h:1") renders as
    "http://h:1/", and issuer checks (RFC 8414 §3.3, RFC 9207 §2.4) are exact string comparisons."""
    return _URL.validate_python(value)


def red(value: str | None, keep: int = 8) -> str | None:
    """Show only the first `keep` characters of a secret value."""
    if value is None:
        return None
    return value[:keep] + "…" if len(value) > keep else value


def jwt_claims(token: str) -> dict:
    """Decode the payload of a JWT for display. No signature check: display only."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _wait_port(port: int, timeout: float = 15.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"port {port} did not open")


@contextmanager
def servers(as_flags: tuple[str, ...] = (), rs_flags: tuple[str, ...] = (), log_name: str = "servers"):
    """Start the AS and the Fernhill resource server, yield, then stop both (always)."""
    DATA.mkdir(parents=True, exist_ok=True)
    logs = DATA / "logs"
    logs.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    procs = []
    try:
        for script, flags, port in (("auth_server.py", as_flags, AS_PORT), ("server.py", rs_flags, RS_PORT)):
            log = open(logs / f"{log_name}.{script.split('.')[0]}.log", "w")
            p = subprocess.Popen([PY, str(HERE / script), *flags], stdout=log, stderr=subprocess.STDOUT,
                                 env=env, start_new_session=True)
            procs.append((p, log))
            _wait_port(port)
        yield
    finally:
        for p, log in procs:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
            log.close()
