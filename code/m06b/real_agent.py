"""The Fernhill agent next to the REAL tool lists of 7 popular MCP servers (saved in data/m06/tools_*.json).
Only Fernhill tools run (in-process); a call to any other tool counts as a wrong pick and is answered "not available here".
Modes: all (every tool loaded) | search (every tool deferred + BM25 tool search). -> data/m06b/<mode>.jsonl"""
import asyncio, copy, json, logging, sys, time
from pathlib import Path
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; CODE = ROOT / "code"
sys.path.insert(0, str(CODE / "agent")); sys.path.insert(0, str(CODE / "fernhill"))
from agent import claude, result_text
from mcp import Client
import server as fernhill, shop
MODE = sys.argv[1]
OTHER = []
for f in sorted((ROOT / "data/m06").glob("tools_*.json")):
    if f.stem != "tools_fernhill": OTHER += json.loads(f.read_text())
QS = ["What does a large latte cost?", "Place an order: one small cold brew for pickup, name Ana.", "What is the status of order A-1041?",
      "Show me the whole menu with prices.", "Read me our refund policy.", "Is oat milk extra on a latte?",
      "Order two oat cookies for delivery to 4 Mill Lane.", "Which drinks come in a large size?",
      "What did order A-1042 contain?", "How much is a double espresso?"]
BASE_ORDERS = copy.deepcopy(shop.ORDERS)
async def one(q):
    shop.ORDERS.clear(); shop.ORDERS.update(copy.deepcopy(BASE_ORDERS))
    async with Client(fernhill.mcp) as c:
        fh = [{"name": f"fernhill__{t.name}", "description": t.description or "", "input_schema": t.input_schema} for t in (await c.list_tools()).tools]
        tools = fh + OTHER
        if MODE == "search":
            tools = [{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}] + [dict(t, defer_loading=True) for t in tools]
        if MODE == "search_pin":   # your own server stays loaded; only the other servers are deferred
            tools = [{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}] + fh + [dict(t, defer_loading=True) for t in OTHER]
        msgs = [{"role": "user", "content": q}]; tin = 0; ms = 0; calls = []
        for _ in range(6):
            t0 = time.perf_counter()
            r = await claude.messages.create(model="claude-haiku-5-5", max_tokens=800, tools=tools, messages=msgs)
            ms += (time.perf_counter() - t0) * 1000; tin += r.usage.input_tokens
            msgs.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in r.content]})
            uses = [b for b in r.content if b.type == "tool_use"]
            if not uses: break
            res = []
            for u in uses:
                calls.append(u.name)
                if u.name.startswith("fernhill__"):
                    out = await c.call_tool(u.name.split("__", 1)[1], u.input); res.append({"type": "tool_result", "tool_use_id": u.id, "content": result_text(out), "is_error": bool(out.is_error)})
                else:
                    res.append({"type": "tool_result", "tool_use_id": u.id, "content": "This tool is not available here.", "is_error": True})
            msgs.append({"role": "user", "content": res})
    answer = "".join(b.text for b in r.content if b.type == "text")
    return {"mode": MODE, "q": q, "calls": calls, "wrong_server_calls": sum(not x.startswith("fernhill__") for x in calls),
            "used_fernhill": any(x.startswith("fernhill__") for x in calls), "input_tokens": tin, "ms": round(ms), "answer": answer[:300]}
async def main():
    rows = [await one(q) for q in QS]
    (ROOT / f"data/m06b/{MODE}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    n = len(rows); print(f"{MODE:6} tools offered={len(OTHER)+4}: used Fernhill {sum(r['used_fernhill'] for r in rows)}/{n} | calls to wrong servers {sum(r['wrong_server_calls'] for r in rows)} "
          f"| avg input tokens {sum(r['input_tokens'] for r in rows)/n:,.0f} | avg time {sum(r['ms'] for r in rows)/n:,.0f} ms")
asyncio.run(main())
