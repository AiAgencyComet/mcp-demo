"""Tool search at 200 tools: all tools deferred (defer_loading), Claude searches with the BM25 or regex tool search tool.
Usage: run_search.py MODEL N_REQUESTS bm25|regex -> data/m05/search.jsonl"""
import json, random, sys, time
from concurrent.futures import ThreadPoolExecutor
from common import BY, CATALOG, DATA, SYSTEM, api, tool_def
MODEL, NREQ, KIND = sys.argv[1], int(sys.argv[2]), sys.argv[3]
keep = json.loads((DATA / "filter.json").read_text())["keep"]
reqs = random.Random(7).sample(keep, min(NREQ, len(keep)))
SEARCH = {"bm25": {"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"},
          "regex": {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}}[KIND]
OUT = DATA / "search.jsonl"; RAW = DATA / "raw_search"; RAW.mkdir(exist_ok=True)
def job(tool):
    tools = [dict(tool_def(t), defer_loading=True) for t in CATALOG]
    random.Random(tool).shuffle(tools)
    msgs = [{"role": "user", "content": BY[tool]["request"]}]
    t0 = time.perf_counter(); r = api.messages.create(model=MODEL, max_tokens=800, system=SYSTEM, tools=[SEARCH] + tools, messages=msgs)
    ms = (time.perf_counter() - t0) * 1000
    picks = [b.name for b in r.content if b.type == "tool_use"]
    searches = [b.input for b in r.content if b.type == "server_tool_use"]
    (RAW / f"{MODEL}_{KIND}_{tool}.json").write_text(r.model_dump_json())
    return {"model": MODEL, "kind": KIND, "tool": tool, "pick": picks[0] if picks else None, "ok": bool(picks) and picks[0] == tool,
            "input_tokens": r.usage.input_tokens, "searches": searches, "ms": round(ms), "stop": r.stop_reason}
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(job, reqs))
with OUT.open("a") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
n = len(rows); print(f"{MODEL} {KIND} 200 deferred: acc={sum(r['ok'] for r in rows)}/{n} = {100*sum(r['ok'] for r in rows)/n:.1f}%  "
      f"avg_in={sum(r['input_tokens'] for r in rows)/n:,.0f}  avg_ms={sum(r['ms'] for r in rows)/n:,.0f}")
print("example searches:", [r["searches"] for r in rows[:3]], "| stops:", {s: sum(1 for r in rows if r['stop']==s) for s in {r['stop'] for r in rows}})
