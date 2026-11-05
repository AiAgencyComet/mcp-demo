"""OLD-spec client (mcp 1.30.0): N refund calls in one session; the person always confirms.
Usage: client_old_refund.py URL N"""
import sys, time
from datetime import timedelta
import anyio
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client

URL, N = sys.argv[1], int(sys.argv[2])

async def confirm(context, params):
    return types.ElicitResult(action="accept", content={"confirm": True})

async def main():
    try:
        async with streamablehttp_client(URL) as (r, w, _):
            async with ClientSession(r, w, read_timeout_seconds=timedelta(seconds=5), elicitation_callback=confirm) as s:
                with anyio.fail_after(6): await s.initialize()
                print("INIT ok", flush=True)
                for i in range(1, N + 1):
                    t0 = time.perf_counter()
                    try:
                        with anyio.fail_after(8):
                            res = await s.call_tool("refund", {"order_id": f"A-{1040 + i}", "amount": 9.40})
                        msg = res.content[0].text if res.content else ""
                        ok = (not res.isError) and msg.startswith("Refunded")
                    except BaseException as e:
                        ok, msg = False, f"{type(e).__name__}: {e}"[:160]
                    print(f"CALL {i} {'ok' if ok else 'err'} {(time.perf_counter()-t0)*1000:.0f} {msg}", flush=True)
    except BaseException as e:
        print(f"FATAL {type(e).__name__}: {str(e)[:160]}", flush=True)

anyio.run(main)
