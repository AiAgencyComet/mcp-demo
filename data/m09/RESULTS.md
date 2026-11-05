# Module 9 · kill test and ask-back across copies (local, 3 server processes on one machine)

Harness: `code/m09/run_kill.py` (3 copies on ports 8121-8123 + `lb.py`, one client makes 20 `get_price` calls, after call 8 the
copy that served the last call gets SIGKILL), `code/m09/run_askback.py` (12 refund calls that ask the person to confirm mid-call).
One run per cell. Old = mcp 1.30.0 / protocol 2025-11-25. New = mcp 2.3.0 / 2026-07-28.

## Kill test (20 plain tool calls, one copy killed after call 8)
| cell | server | client | load balancer | ok |
|---|---|---|---|---|
| old_rr | stateful (FastMCP default) | SDK default | round robin | 0/20 |
| old_sticky | stateful (FastMCP default) | SDK default (gives up on 404: "Session terminated") | sticky | 8/20 (all 8 before the kill, 0/12 after) |
| old_reinit_sticky | stateful | follows the 2025-11-25 MUST: new session on 404 (`client_old_reinit.py`) | sticky | 20/20 (1 re-init; call 9 took 47 ms vs 5 ms) |
| old_reinit_rr | stateful | re-initializes on 404 | round robin | 6/20 (14 re-inits) |
| old_stateless_rr | `stateless_http=True` (no session ID) | SDK default | round robin | 20/20 |
| old_stateless_sticky | `stateless_http=True` | SDK default | sticky | 20/20 |
| new_rr / new_sticky | MCPServer (no sessions in the spec) | SDK default | either | 20/20 |
Spec, 2025-11-25 transports: on HTTP 404 for a request with a session ID, the client "MUST start a new session by sending a new
InitializeRequest without a session ID attached". The SDK 1.30 client raises "Session terminated" instead (`client/streamable_http.py:372`).

## Ask-back (12 refunds; the tool asks the person to confirm mid-call; the person always accepts)
| cell | server | load balancer | ok |
|---|---|---|---|
| askback_old_stateful_direct | stateful, 1 copy | none | 12/12 |
| askback_old_stateful_sticky | stateful, 3 copies | sticky | 12/12 (every refund pinned to the session's copy) |
| askback_old_stateful_rr | stateful, 3 copies | round robin | 0/12 (timeout: the answer reaches another copy) |
| askback_old_stateless_direct | `stateless_http=True`, 1 copy | none | 0/12 (timeout even on ONE copy) |
| askback_old_stateless_rr | `stateless_http=True`, 3 copies | round robin | 0/12 |
| new spec (module 7, data/m07) | MRTR, one shared key | round robin | 12/12 (per-process keys: 0/12) |

## The honest reading
On the old spec a server could scale out freely (stateless mode, or stateful + sticky + a client that re-initializes), or it could
ask the person mid-call (stateful, pinned to one copy), not both. The 2026-07-28 spec gives both: no session, and ask-back that
works on any copy (multi round-trip with a shared key). The old 8/20 is the old SDK's default client, not the old spec.
