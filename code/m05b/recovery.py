"""Error recovery: does the model recover when the tool error is hidden vs when it carries a hint?
Same Fernhill server; only the exception type changes (ValueError = hidden, ToolError = shown).
Usage: recovery.py RUNS -> data/m05b/recovery.jsonl + summary"""
import asyncio, copy, json, logging, re, sys, types
from pathlib import Path
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; CODE = ROOT / "code"
sys.path.insert(0, str(CODE / "agent")); sys.path.insert(0, str(CODE / "fernhill"))
from agent import run
import shop
SRC = (CODE / "fernhill" / "server.py").read_text().replace('if __name__ == "__main__":', 'if False:')
# experiment-only rule the menu cannot show: today's stock (cold brew is sold out)
SRC = SRC.replace("    total = round(", "    for it in items:\n        if shop.STOCK.get(it.drink, 1) <= 0:\n            raise ToolError(f\"{it.drink} is sold out today. Offer a latte or a flat white instead.\")\n    total = round(", 1)
BASE_ORDERS = copy.deepcopy(shop.ORDERS)

def make_server(hidden: bool):
    src = SRC.replace("raise ToolError(", "raise ValueError(") if hidden else SRC
    mod = types.ModuleType(f"fernhill_{'hidden' if hidden else 'hint'}"); exec(compile(src, "server.py", "exec"), mod.__dict__)
    return mod.mcp

CASES = [
  {"id": "soldout", "q": "Order a large cold brew for pickup, name Cy.", "cause": r"sold out|out of stock|none left|not available today|unavailable"},
  {"id": "refund", "q": "Refund order A-9999, the customer was unhappy.", "cause": r"(no order|not find|couldn't find|could not find|doesn't exist|does not exist|no record|isn't|is not) "},
  {"id": "size", "q": "Order a large flat white for pickup, name Ana.", "cause": r"\bsmall\b"},
  {"id": "menu", "q": "Order a mocha for pickup, name Ben.", "cause": r"(not (on|in) (the|our) menu|isn't on|is not on|no mocha|doesn't (list|have|offer)|don't (have|offer|serve))"},
  {"id": "order", "q": "What is the status of order B-2001?", "cause": r"(no order|not find|couldn't find|could not find|doesn't exist|does not exist|no record|A-\d{4})"},
]

async def main():
    runs = int(sys.argv[1]); rows = []
    for hidden in (True, False):
        for case in CASES:
            for i in range(runs):
                shop.ORDERS.clear(); shop.ORDERS.update(copy.deepcopy(BASE_ORDERS)); shop.STOCK["cold brew"] = 0
                m = await run(case["q"], {"fernhill": make_server(hidden)}, model="claude-haiku-5-5", max_turns=6)
                ans = m["answer"] or ""
                rows.append({"cond": "hidden" if hidden else "hint", "case": case["id"], "i": i,
                             "named_cause": bool(re.search(case["cause"], ans, re.I)),
                             "errors_seen": sum(c["is_error"] for c in m["tool_calls"]), "calls": len(m["tool_calls"]),
                             "tools": [c["tool"] for c in m["tool_calls"]], "first_error": next((c["result"] for c in m["tool_calls"] if c["is_error"]), None),
                             "answer": ans[:500], "input_tokens": m["input_tokens"]})
    out = ROOT / "data/m05b/recovery.jsonl"; out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    for cond in ("hidden", "hint"):
        for case in CASES:
            sel = [r for r in rows if r["cond"] == cond and r["case"] == case["id"]]
            print(f"{cond:6} {case['id']:5}: named the real cause {sum(r['named_cause'] for r in sel)}/{len(sel)} | avg tool calls {sum(r['calls'] for r in sel)/len(sel):.1f} | avg in-tokens {sum(r['input_tokens'] for r in sel)/len(sel):,.0f}")
    for cond in ("hidden", "hint"):
        r = next(r for r in rows if r["cond"] == cond and r["case"] == "soldout")
        print(f"\n[{cond}] error the model saw: {r['first_error']}\n[{cond}] answer: {r['answer'][:260]}")

asyncio.run(main())
