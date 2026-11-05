"""Tool-choice accuracy vs number of tools. Usage: run_choice.py MODEL N_REQUESTS SIZES [vague]
For each request, the tool set = its correct tool + (N-1) other tools from the catalog (seeded), shuffled.
Appends to data/m05/choice.jsonl (resumable); raw responses to data/m05/raw_choice/."""
import json, random, sys
from concurrent.futures import ThreadPoolExecutor
from common import BY, CATALOG, DATA, OPAQUE, VOID, choose, tool_def
MODEL, NREQ, SIZES = sys.argv[1], int(sys.argv[2]), [int(x) for x in sys.argv[3].split(",")]
MODE = sys.argv[4] if len(sys.argv) > 4 else "good"
VAGUE = MODE in ("vague", "opaque_vague", "bare", "blind", "void"); OPQ = MODE.startswith("opaque") or MODE in ("bare", "blind", "void")
SCHEMA = MODE if MODE in ("bare", "blind", "void") else "full"
keep = json.loads((DATA / "filter.json").read_text())["keep"]
reqs = random.Random(7).sample(keep, min(NREQ, len(keep)))
OUT = DATA / "choice.jsonl"; RAW = DATA / "raw_choice"; RAW.mkdir(exist_ok=True)
done = set()
if OUT.exists():
    for l in OUT.read_text().splitlines():
        r = json.loads(l); done.add((r["model"], r["n"], r["tool"], r.get("mode", "vague" if r.get("vague") else "good")))
def job(args):
    n, tool = args
    if (MODEL, n, tool, MODE) in done: return None
    rng = random.Random(f"{n}-{tool}")
    others = [t["full"] for t in CATALOG if t["full"] != tool]
    names = [tool] + rng.sample(others, n - 1); rng.shuffle(names)
    r = choose(MODEL, BY[tool]["request"], [tool_def(BY[x], vague=VAGUE, opaque=OPQ, schema=SCHEMA) for x in names])
    want = VOID[tool] if MODE == "void" else (OPAQUE[tool] if OPQ else tool)
    row = {"model": MODEL, "n": n, "tool": tool, "vague": VAGUE, "mode": MODE, "pick": r["picks"][0] if r["picks"] else None,
           "ok": bool(r["picks"]) and r["picks"][0] == want, "input_tokens": r["input_tokens"], "ms": round(r["ms"])}
    (RAW / f"{MODEL}_{n}_{MODE}_{tool}.json").write_text(json.dumps(r["raw"]))
    return row
jobs = [(n, t) for n in SIZES for t in reqs]
with ThreadPoolExecutor(8) as ex, OUT.open("a") as f:
    for row in ex.map(job, jobs):
        if row: f.write(json.dumps(row) + "\n"); f.flush()
rows = [json.loads(l) for l in OUT.read_text().splitlines()]
for n in SIZES:
    sel = [r for r in rows if r["model"] == MODEL and r["n"] == n and r.get("mode", "vague" if r["vague"] else "good") == MODE and r["tool"] in reqs]
    if sel: print(f"{MODEL} n={n:3} {MODE:12} acc={sum(r['ok'] for r in sel)}/{len(sel)} "
                  f"= {100*sum(r['ok'] for r in sel)/len(sel):.1f}%  avg_in={sum(r['input_tokens'] for r in sel)/len(sel):,.0f}  "
                  f"avg_ms={sum(r['ms'] for r in sel)/len(sel):,.0f}")
