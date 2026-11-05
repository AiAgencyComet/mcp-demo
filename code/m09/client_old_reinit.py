"""Old-spec client (mcp 1.30.0) that follows the 2025-11-25 rule: on HTTP 404 for a session ID, the client
MUST start a new session (new InitializeRequest, no session ID). One retry per call. Usage: client_old_reinit.py URL N GAP"""
import sys, time
from contextlib import AsyncExitStack
from datetime import timedelta
import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL, N, GAP = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])

async def open_session(stack):
    r, w, _ = await stack.enter_async_context(streamablehttp_client(URL))
    s = await stack.enter_async_context(ClientSession(r, w, read_timeout_seconds=timedelta(seconds=4)))
    with anyio.fail_after(6): await s.initialize()
    return s

async def main():
    reinits = 0
    stack = AsyncExitStack(); await stack.__aenter__()
    try:
        s = await open_session(stack); print("INIT ok", flush=True)
        for i in range(1, N + 1):
            t0 = time.perf_counter(); ok, msg = False, ""
            for attempt in (1, 2):
                try:
                    with anyio.fail_after(6):
                        res = await s.call_tool("get_price", {"drink": "latte"})
                    ok = not res.isError; msg = res.content[0].text if res.content else ""; break
                except BaseException as e:
                    msg = f"{type(e).__name__}: {e}"[:160]
                    if attempt == 1 and "terminated" in str(e).lower():
                        try: await stack.aclose()
                        except BaseException: pass
                        stack = AsyncExitStack(); await stack.__aenter__()
                        try:
                            s = await open_session(stack); reinits += 1; print(f"REINIT {reinits}", flush=True)
                        except BaseException as e2:
                            msg = f"reinit failed: {type(e2).__name__}: {e2}"[:160]; break
                    else: break
            print(f"CALL {i} {'ok' if ok else 'err'} {(time.perf_counter()-t0)*1000:.0f} {msg}", flush=True)
            await anyio.sleep(GAP)
    except BaseException as e:
        print(f"FATAL {type(e).__name__}: {str(e)[:160]}", flush=True)
    finally:
        try: await stack.aclose()
        except BaseException: pass
    print(f"REINITS {reinits}", flush=True)

anyio.run(main)
