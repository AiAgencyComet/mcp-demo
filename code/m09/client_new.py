"""New-spec client (mcp 2.3.0, protocol 2026-07-28): N tool calls. Usage: client_new.py URL N GAP"""
import sys, time
import anyio
from mcp import Client

URL, N, GAP = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])

async def main():
    try:
        async with Client(URL, read_timeout_seconds=4) as c:
            print("INIT ok", flush=True)
            for i in range(1, N + 1):
                t0 = time.perf_counter()
                try:
                    with anyio.fail_after(6):
                        res = await c.call_tool("get_price", {"drink": "latte"})
                    ok = not res.is_error
                    msg = res.content[0].text if res.content else ""
                except BaseException as e:
                    ok, msg = False, f"{type(e).__name__}: {e}"[:160]
                print(f"CALL {i} {'ok' if ok else 'err'} {(time.perf_counter()-t0)*1000:.0f} {msg}", flush=True)
                await anyio.sleep(GAP)
    except BaseException as e:
        print(f"FATAL {type(e).__name__}: {str(e)[:160]}", flush=True)

anyio.run(main)
