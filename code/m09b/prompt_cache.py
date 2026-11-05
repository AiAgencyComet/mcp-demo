"""Stable vs shuffled tool lists and Claude prompt caching. 50 tools (catalog from module 5), cache_control on the
last tool, 10 requests each, claude-haiku-5-5. -> data/m09b/prompt_cache.json"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m05"))
from common import CATALOG, api, tool_def
ROOT = Path(__file__).resolve().parents[2]
BASE = [tool_def(t) for t in CATALOG[:50]]
QS = ["Show me every pastry on the menu.", "What is the stock level of oat milk?", "List today's refunds.", "Book the back room for Friday.",
      "Draft an email to the bean supplier.", "What are this week's sales?", "Who works the Saturday shift?", "Post our new pumpkin latte.",
      "What is the status of order A-1041?", "Show unpaid supplier invoices."]
def run(shuffle):
    rows = []
    for i, q in enumerate(QS):
        tools = [dict(t) for t in BASE]
        if shuffle: random.Random(i).shuffle(tools)
        tools[-1]["cache_control"] = {"type": "ephemeral"}
        r = api.messages.create(model="claude-haiku-5-5", max_tokens=300, tools=tools, messages=[{"role": "user", "content": q}])
        u = r.usage; rows.append({"input": u.input_tokens, "cache_read": u.cache_read_input_tokens or 0, "cache_write": u.cache_creation_input_tokens or 0})
    return rows
out = {}
for name, sh in (("stable", False), ("shuffled", True)):
    rows = run(sh); out[name] = rows
    # Haiku 5.5: input $0.10/M, cache write (5m) $0.125/M, cache read $0.01/M
    cost = sum(r["input"] * 0.10 + r["cache_write"] * 0.125 + r["cache_read"] * 0.01 for r in rows) / 1e6
    print(f"{name:8}: cache_read {sum(r['cache_read'] for r in rows):7,}  cache_write {sum(r['cache_write'] for r in rows):7,}  uncached {sum(r['input'] for r in rows):6,}  input cost ${cost:.5f}")
(ROOT / "data/m09b/prompt_cache.json").write_text(json.dumps(out, indent=1))
