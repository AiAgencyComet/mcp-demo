"""Module 1: the same question answered three ways, measured.
  1. API        : your Python code calls the shop function directly (no model).
  2. Tool call  : Claude gets the tool in code (function calling) and your code runs it.
  3. MCP tool   : Claude gets the same tool from the Fernhill MCP server over Streamable HTTP.
Usage: three_ways.py RUNS  -> data/m01/three_ways.json"""
import asyncio, json, logging, socket, subprocess, sys, time
from pathlib import Path
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; CODE = ROOT / "code"
sys.path.insert(0, str(CODE / "agent")); sys.path.insert(0, str(CODE / "fernhill"))
import anthropic
from agent import claude, run
import shop

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
Q = "What does a large latte cost at Fernhill?"
MODEL = "claude-haiku-5-5"

from price import get_price

TOOL = {"name": "get_price", "description": "Return the price of one drink in US dollars.",
        "input_schema": {"type": "object", "properties": {"drink": {"type": "string"}}, "required": ["drink"]}}

async def way_api():
    t0 = time.perf_counter(); p = get_price("latte"); return {"ms": (time.perf_counter() - t0) * 1000, "answer": p, "tokens": 0}

async def way_tool():
    msgs = [{"role": "user", "content": Q}]; tin = tout = 0; t0 = time.perf_counter(); code_ms = 0
    for _ in range(4):
        r = await claude.messages.create(model=MODEL, max_tokens=400, tools=[TOOL], messages=msgs)
        tin += r.usage.input_tokens; tout += r.usage.output_tokens
        msgs.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in r.content]})
        uses = [b for b in r.content if b.type == "tool_use"]
        if not uses: break
        res = []
        for u in uses:
            t1 = time.perf_counter(); out = get_price(u.input["drink"]); code_ms += (time.perf_counter() - t1) * 1000
            res.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
        msgs.append({"role": "user", "content": res})
    return {"ms": (time.perf_counter() - t0) * 1000, "tool_ms": code_ms, "input_tokens": tin, "output_tokens": tout,
            "answer": "".join(b.text for b in r.content if b.type == "text")}

async def way_mcp(url):
    t0 = time.perf_counter()
    m = await run(Q, {"fernhill": url}, model=MODEL)
    return {"ms": (time.perf_counter() - t0) * 1000, "tool_ms": m["mcp_ms"], "input_tokens": m["input_tokens"],
            "output_tokens": m["output_tokens"], "answer": m["answer"], "tools": [c["tool"] for c in m["tool_calls"]]}

def wait(p):
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)

async def main():
    srv = subprocess.Popen([CODE / ".venv-new/bin/python", Path(__file__).resolve().parent / "price_server.py", "8210"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); wait(8210)
    try:
        rows = {"api": [], "tool": [], "mcp": []}
        for i in range(RUNS):
            rows["api"].append(await way_api())
            rows["tool"].append(await way_tool())
            rows["mcp"].append(await way_mcp("http://127.0.0.1:8210/mcp"))
    finally:
        srv.terminate(); srv.wait(5)
    med = lambda xs: sorted(xs)[len(xs) // 2]
    summary = {k: {"median_ms": round(med([r["ms"] for r in v]), 2),
                   "median_tool_ms": round(med([r.get("tool_ms", 0) for r in v]), 2),
                   "median_input_tokens": med([r.get("input_tokens", 0) for r in v])} for k, v in rows.items()}
    (ROOT / "data/m01/three_ways.json").write_text(json.dumps({"question": Q, "model": MODEL, "runs": RUNS, "summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1)); print("tool answer:", rows["tool"][0]["answer"][:120]); print("mcp answer:", rows["mcp"][0]["answer"][:120], rows["mcp"][0]["tools"])

asyncio.run(main())
