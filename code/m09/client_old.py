"""Old-spec client (mcp 1.30.0): one session, N tool calls. Usage: client_old.py URL N GAP"""
import sys, time
from datetime import timedelta
import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL, N, GAP = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])

async def main():
    try:
        async with streamablehttp_client(URL) as (r, w, _):
            async with ClientSession(r, w, read_timeout_seconds=timedelta(seconds=4)) as s:
                with anyio.fail_after(6): await s.initialize()
                print("INIT ok", flush=True)
                for i in range(1, N + 1):
                    t0 = time.perf_counter()
                    try:
                        with anyio.fail_after(6):
                            res = await s.call_tool("get_price", {"drink": "latte"})
                        ok = not res.isError
                        msg = res.content[0].text if res.content else ""
                    except BaseException as e:
                        ok, msg = False, f"{type(e).__name__}: {e}"[:160]
                    print(f"CALL {i} {'ok' if ok else 'err'} {(time.perf_counter()-t0)*1000:.0f} {msg}", flush=True)
                    await anyio.sleep(GAP)
    except BaseException as e:
        print(f"FATAL {type(e).__name__}: {str(e)[:160]}", flush=True)

anyio.run(main)
