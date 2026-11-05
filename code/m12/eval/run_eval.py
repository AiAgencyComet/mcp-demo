"""Tool-choice eval for a Fernhill release. The gate runs before release, like a unit test, but with a real model.

  python eval/run_eval.py v1              # baseline (the released server)
  python eval/run_eval.py v2_bad          # the refactor PR -> compared with the baseline, exit 1 if it regresses
  python eval/run_eval.py abl_names|abl_docs|abl_fields   # one change at a time (definitions transformed from v1)

For each request: the model sees the release's tools (from MCP tools/list) + 5 tools of other servers.
Score 1 "choice": the first tool call is the labelled tool.
Score 2 "call":   that call runs on the real release server and has the right effect (right items, name, order ID).
Raw responses are cached in data/m12/raw/<release>/ ; a second run re-scores from the cache with no API cost."""
import asyncio, copy, hashlib, json, logging, sys, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE.parents[1] / "fernhill"), str(HERE)]
logging.disable(logging.WARNING)            # the SDK logs every ToolError traceback; keep the eval output clean

import anthropic
import mcp_types as types
from dotenv import load_dotenv
from mcp import Client

import server as v1                        # code/fernhill/server.py
import shop
from cases import CASES, DISTRACTORS, HOLDOUT
from releases import fernhill_v1_1 as v1_1
from releases import fernhill_v2_bad as v2

load_dotenv(ROOT / "code" / ".env")
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50           # USD per million tokens
REPS = 3
SYSTEM = ("You are the assistant of the manager of Fernhill Coffee. "
          "Do the request by calling exactly one tool. Do not ask questions.")
GATE = {"max_drop_pts": 5.0, "min_choice_pct": 80.0}   # fixed before the first run
OUT = ROOT / "data" / "m12"
PREFIX = "fernhill__"
V1_NAMES = ["get_menu", "place_order", "order_status", "refund"]


# ---------- releases ----------

def strip_descriptions(x):
    if isinstance(x, dict): return {k: strip_descriptions(v) for k, v in x.items() if k != "description"}
    if isinstance(x, list): return [strip_descriptions(v) for v in x]
    return x

def p_fields(schema):
    s = copy.deepcopy(schema); props = s.get("properties", {})
    ren = {n: f"p{i + 1}" for i, n in enumerate(props)}
    s["properties"] = {ren[n]: ({**v, "title": f"P{i + 1}"} if "title" in v else v) for i, (n, v) in enumerate(props.items())}
    if "required" in s: s["required"] = [ren[n] for n in s["required"]]
    return s, {v: k for k, v in ren.items()}

class Release:
    """What the model sees (tools/list of `see`, then an optional transform) and where the call runs (`run`)."""
    def __init__(self, name, see, run, labels=None, rename=False, docs=False, fields=False, desc=None):
        self.name, self.see, self.run = name, see, run
        self.labels = labels or {n: n for n in V1_NAMES}
        self.rename, self.docs, self.fields, self.desc = rename, docs, fields, desc or {}
        self.back_name, self.back_args = {}, {}

    async def claude_tools(self):
        async with Client(self.see) as c:
            listed = (await c.list_tools()).tools
        out = []
        for t in listed:
            name, desc, schema = t.name, t.description or "", t.input_schema
            if self.rename:
                name = v2.LABELS[t.name]
            if t.name in self.desc:
                desc = self.desc[t.name](desc)
            if self.docs:
                desc, schema = "Tool.", strip_descriptions(schema)
            if self.fields:
                schema, back = p_fields(schema); self.back_args[name] = back
            self.back_name[name] = t.name
            out.append({"name": PREFIX + name, "description": desc, "input_schema": schema})
        return out

    def to_run(self, name, args):
        """Map the model's call (release names) to the server that runs it."""
        back = self.back_args.get(name, {})
        return self.back_name.get(name, name), {back.get(k, k): v for k, v in args.items()}

RELEASES = {
    "v1":         lambda: Release("v1", v1.mcp, v1.mcp),
    "v1_1":       lambda: Release("v1_1", v1_1.mcp, v1_1.mcp),
    "v2_bad":     lambda: Release("v2_bad", v2.mcp, v2.mcp, labels=v2.LABELS),
    "abl_names":  lambda: Release("abl_names", v1.mcp, v1.mcp, labels=v2.LABELS, rename=True),
    "abl_docs":   lambda: Release("abl_docs", v1.mcp, v1.mcp, docs=True),
    "abl_fields": lambda: Release("abl_fields", v1.mcp, v1.mcp, fields=True),
    # the v2 refactor (rename + "Tool." + p1..) applied to v1.1 instead of v1: same logic as v1.1, only the view changes
    "v2_on_v1_1": lambda: Release("v2_on_v1_1", v1_1.mcp, v1_1.mcp, labels=v2.LABELS, rename=True, docs=True, fields=True),
    # description-only PRs on top of v1.1 (same names, same schema; the call runs on the v1.1 server)
    "v1_2_swap":  lambda: Release("v1_2_swap", v1_1.mcp, v1_1.mcp, desc={      # copy-paste error: two docstrings swapped
        "order_status": lambda d: SWAP_REFUND_DOC,
        "refund": lambda d: "Return the status of one order."}),
    "v1_2_first": lambda: Release("v1_2_first", v1_1.mcp, v1_1.mcp, desc={     # "helpful" hint added to one tool
        "get_menu": lambda d: d + " Call this tool first, before any other Fernhill tool, so that you know the menu."}),
}
SWAP_REFUND_DOC = ("Refund one order: give the money back to the customer. "
                   "The server asks the person to confirm, so call this tool at once.")


# ---------- model calls (cached) ----------

async def ask(api, sem, raw_dir, tools, tools_sha, case_id, request, rep, fresh, max_tokens=600):
    path = raw_dir / f"{case_id}_r{rep}.json"
    if path.exists() and not fresh:
        rec = json.loads(path.read_text())
        if rec["tools_sha"] == tools_sha:
            return rec
    async with sem:
        t0 = time.perf_counter()
        r = await api.messages.create(model=MODEL, max_tokens=max_tokens, system=SYSTEM, tools=tools,
                                      tool_choice={"type": "auto"}, messages=[{"role": "user", "content": request}])
        ms = (time.perf_counter() - t0) * 1000
    rec = {"case_id": case_id, "rep": rep, "request": request, "model": MODEL, "system": SYSTEM,
           "tools_sha": tools_sha, "max_tokens": max_tokens, "ms": round(ms), "response": r.model_dump(mode="json")}
    path.write_text(json.dumps(rec, indent=1))
    return rec


# ---------- run the call on the real server and check the effect ----------

async def say_yes(ctx, params):
    return types.ElicitResult(action="accept", content={"confirm": True})

def check_order(stored, exp):
    got = sorted((i["drink"], i["size"]) for i in stored["items"])
    if got != sorted((i["drink"], i["size"]) for i in exp["items"]):
        return f"items {got}"
    for e in exp["items"]:
        if "milk" in e and not any(i["drink"] == e["drink"] and i["milk"] == e["milk"] for i in stored["items"]):
            return f"milk for {e['drink']}"
    h, eh = stored["handoff"], exp["handoff"]
    if h.get("kind") != eh["kind"]: return f"handoff {h.get('kind')}"
    if "name" in eh and h.get("name", "").strip().lower() != eh["name"].lower(): return f"name {h.get('name')!r}"
    if "address_has" in eh and eh["address_has"].lower() not in h.get("address", "").lower(): return f"address {h.get('address')!r}"
    return None

async def run_call(rel, label, expect, name, args, base_orders):
    shop.ORDERS.clear(); shop.ORDERS.update(copy.deepcopy(base_orders))
    run_name, run_args = rel.to_run(name, args)
    try:
        async with Client(rel.run, elicitation_callback=say_yes) as c:
            r = await c.call_tool(run_name, run_args)
    except Exception as e:                                    # noqa: BLE001
        return False, f"exception {type(e).__name__}: {e}"[:200]
    text = " ".join(getattr(x, "text", "") for x in r.content)
    if r.is_error:
        return False, "is_error: " + text[:200]
    sc = r.structured_content or {}
    if label == "get_menu":
        return True, None
    if label == "place_order":
        why = check_order(shop.ORDERS[sc["order_id"]], expect)
        return why is None, why
    if label == "order_status":
        ok = sc.get("order_id") == expect["order_id"]
        return ok, None if ok else f"order_id {sc.get('order_id')}"
    if label == "refund":
        ok = text.startswith("Refunded") and f"for {expect['order_id']}." in text
        return ok, None if ok else text[:120]
    return False, "no check"


# ---------- main ----------

async def main(rel_name, fresh=False, case_set="main", baseline="v1", max_tokens=600):
    rel = RELEASES[rel_name]()
    cases = CASES if case_set == "main" else HOLDOUT
    tag = rel_name + ("" if case_set == "main" else "_" + case_set) + ("" if max_tokens == 600 else f"_mt{max_tokens}")
    tools = await rel.claude_tools() + DISTRACTORS
    tools_sha = hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()[:16]
    raw_dir = OUT / "raw" / tag; raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "_tools_offered.json").write_text(json.dumps(tools, indent=1))

    api = anthropic.AsyncAnthropic(max_retries=6); sem = asyncio.Semaphore(8)
    jobs = [(cid, req, rep) for cid, req, _, _ in cases for rep in range(1, REPS + 1)]
    recs = await asyncio.gather(*[ask(api, sem, raw_dir, tools, tools_sha, cid, req, rep, fresh, max_tokens) for cid, req, rep in jobs])

    base_orders = copy.deepcopy(shop.ORDERS)
    by_case = {c[0]: c for c in cases}
    rows = []
    for rec in recs:
        cid, request, label, expect = by_case[rec["case_id"]]
        resp = rec["response"]
        uses = [b for b in resp["content"] if b["type"] == "tool_use"]
        want = PREFIX + rel.labels[label] if label in V1_NAMES else label
        pick = uses[0]["name"] if uses else None
        choice_ok = pick == want
        call_ok, why = (choice_ok, None)
        if choice_ok and label in V1_NAMES:
            call_ok, why = await run_call(rel, label, expect, pick[len(PREFIX):], uses[0]["input"], base_orders)
        rows.append({"case_id": cid, "rep": rec["rep"], "label": label, "want": want, "pick": pick,
                     "args": uses[0]["input"] if uses else None, "choice_ok": choice_ok, "call_ok": call_ok, "why": why,
                     "stop": resp["stop_reason"], "in_tok": resp["usage"]["input_tokens"], "out_tok": resp["usage"]["output_tokens"], "ms": rec["ms"],
                     "text": "".join(b.get("text", "") for b in resp["content"] if b["type"] == "text")[:200]})
    shop.ORDERS.clear(); shop.ORDERS.update(base_orders)

    pct = lambda rs, k: round(100 * sum(r[k] for r in rs) / len(rs), 1)
    fern = [r for r in rows if r["label"] in V1_NAMES]; other = [r for r in rows if r["label"] not in V1_NAMES]
    groups = {g: [r for r in rows if r["case_id"].startswith(g)] for g in ("menu", "order", "status", "refund", "other")}
    in_tok = sum(r["in_tok"] for r in rows); out_tok = sum(r["out_tok"] for r in rows)
    summary = {
        "release": rel_name, "case_set": case_set, "max_tokens": max_tokens, "model": MODEL, "reps": REPS, "runs": len(rows), "tools_offered": len(tools), "tools_sha": tools_sha,
        "choice_pct": pct(rows, "choice_ok"), "fernhill_choice_pct": pct(fern, "choice_ok"),
        "fernhill_call_pct": pct(fern, "call_ok"), "other_servers_choice_pct": pct(other, "choice_ok"),
        "by_group_choice_pct": {g: pct(rs, "choice_ok") for g, rs in groups.items()},
        "by_group_call_pct": {g: pct(rs, "call_ok") for g, rs in groups.items() if g != "other"},
        "per_rep_choice_pct": {rep: pct([r for r in rows if r["rep"] == rep], "choice_ok") for rep in range(1, REPS + 1)},
        "no_tool_call": sum(r["pick"] is None for r in rows),
        "stop_max_tokens": sum(r["stop"] == "max_tokens" for r in rows),
        "wrong_picks": Counter(f"{r['want']} -> {r['pick']}" for r in rows if not r["choice_ok"]).most_common(),
        "call_failures": Counter(f"{r['case_id']}: {r['why']}" for r in fern if r["choice_ok"] and not r["call_ok"]).most_common(),
        "input_tokens": in_tok, "output_tokens": out_tok, "avg_input_tokens": round(in_tok / len(rows)),
        "cost_usd": round(in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT, 4),
        "avg_ms": round(sum(r["ms"] for r in rows) / len(rows)),
    }

    verdict, reasons = "PASS", []
    base_path = OUT / (f"eval_{baseline}.json" if case_set == "main" else f"eval_{baseline}_{case_set}.json")
    if summary["choice_pct"] < GATE["min_choice_pct"]:
        reasons.append(f"choice {summary['choice_pct']}% < {GATE['min_choice_pct']}%")
    if rel_name != "v1" and base_path.exists():
        base = json.loads(base_path.read_text())["summary"]
        for k in ("choice_pct", "fernhill_call_pct"):
            drop = round(base[k] - summary[k], 1)
            if drop > GATE["max_drop_pts"]:
                reasons.append(f"{k} dropped {drop} pts ({base[k]}% -> {summary[k]}%)")
    if reasons: verdict = "FAIL"
    summary["gate"] = {"rule": GATE, "baseline": baseline if rel_name != "v1" else None, "verdict": verdict, "reasons": reasons}
    (OUT / f"eval_{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))

    print(f"release {rel_name} ({case_set} set)  model {MODEL}  {len(cases)} requests x {REPS} reps = {len(rows)} runs  "
          f"tools offered {len(tools)}  avg input {summary['avg_input_tokens']} tok")
    print(f"  tool choice (all)        {summary['choice_pct']:5.1f}%   per rep {list(summary['per_rep_choice_pct'].values())}")
    print(f"  tool choice (Fernhill)   {summary['fernhill_choice_pct']:5.1f}%")
    print(f"  call has right effect    {summary['fernhill_call_pct']:5.1f}%")
    print(f"  other servers kept       {summary['other_servers_choice_pct']:5.1f}%")
    print("  by group (choice/call)  " + "  ".join(
        f"{g} {summary['by_group_choice_pct'][g]:.0f}/{summary['by_group_call_pct'].get(g, summary['by_group_choice_pct'][g]):.0f}"
        for g in groups))
    print(f"  no tool call {summary['no_tool_call']}   stopped by max_tokens {summary['stop_max_tokens']}   cost ${summary['cost_usd']}   avg {summary['avg_ms']} ms")
    for w, n in summary["wrong_picks"][:8]: print(f"    wrong x{n}: {w}")
    for w, n in summary["call_failures"][:8]: print(f"    call fail x{n}: {w}")
    print(f"GATE {verdict} (baseline {baseline})" + ("".join(f"\n  - {r}" for r in reasons)))
    return 0 if verdict == "PASS" else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], fresh="--fresh" in sys.argv,
                                case_set="holdout" if "--holdout" in sys.argv else "main",
                                baseline=sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else "v1",
                                max_tokens=int(sys.argv[sys.argv.index("--max-tokens") + 1]) if "--max-tokens" in sys.argv else 600)))
