"""Join the host and server span files into one tree per trace.
  -> data/m12/trace/trace.json (nested) and trace_tree.txt (readable)
First it redacts account identifiers that the Claude SDK span carries by default, and local paths."""
import json, re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "m12" / "trace"
REDACT_KEYS = {"anthropic.organization.id": "<org-id redacted>", "anthropic.workspace.id": "<workspace-id redacted>"}
HOME = re.compile(r"/Users/[^/\s\"']+/")


def redact_file(path):
    lines = []
    for line in path.read_text().splitlines():
        s = json.loads(line)
        for k, v in REDACT_KEYS.items():
            if k in s.get("attributes", {}): s["attributes"][k] = v
        lines.append(HOME.sub("~/", json.dumps(s)))
    path.write_text("\n".join(lines) + "\n")
    return [json.loads(l) for l in lines]


def t(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000

def label(s):
    a = s["attributes"]; bits = []
    if s["name"] == "anthropic.messages.create":
        bits.append(f"{a.get('gen_ai.request.model')}  in {a.get('gen_ai.usage.input_tokens')} / out {a.get('gen_ai.usage.output_tokens')} tok"
                    f" (thinking {a.get('gen_ai.usage.reasoning.output_tokens')})  stop {a.get('anthropic.message.stop_reason')}")
    for k in ("fernhill.order.id", "fernhill.order.total", "error.type"):
        if k in a: bits.append(f"{k.split('.')[-1]}={a[k]}")
    if s["status"]["status_code"] == "ERROR": bits.append("STATUS=ERROR")
    return "  ".join(bits)


def main():
    host = redact_file(OUT / "host_spans.jsonl"); server = redact_file(OUT / "server_spans.jsonl")
    spans = {}
    for s in host + server:
        spans[s["context"]["span_id"]] = {
            "name": s["name"], "service": s["resource"]["attributes"]["service.name"], "kind": s["kind"].split(".")[-1],
            "trace_id": s["context"]["trace_id"], "span_id": s["context"]["span_id"], "parent_id": s["parent_id"],
            "start_ms": t(s["start_time"]), "ms": round(t(s["end_time"]) - t(s["start_time"]), 2),
            "status": s["status"]["status_code"], "attributes": s["attributes"], "label": label(s), "children": []}
    roots = []
    for sp in spans.values():
        (spans[sp["parent_id"]]["children"] if sp["parent_id"] in spans else roots).append(sp)
    for sp in spans.values(): sp["children"].sort(key=lambda c: c["start_ms"])
    roots.sort(key=lambda r: r["start_ms"])

    cross = sum(1 for sp in spans.values() if sp["service"] == "fernhill-mcp-server" and sp["parent_id"] in spans
                and spans[sp["parent_id"]]["service"] == "fernhill-host")
    lines = [f"{len(spans)} spans from 2 processes, {len(roots)} traces, {cross} server spans whose parent is a host span"]
    def walk(sp, prefix, last, depth):
        tag = "[host]  " if sp["service"] == "fernhill-host" else "[server]"
        branch = "" if depth == 0 else prefix + ("└─ " if last else "├─ ")
        lines.append(f"{tag} {branch}{sp['name']}  ({sp['kind']}, {sp['ms']:.1f} ms)" + (f"  {sp['label']}" if sp["label"] else ""))
        kids = sp["children"]
        for i, c in enumerate(kids):
            walk(c, "" if depth == 0 else prefix + ("   " if last else "│  "), i == len(kids) - 1, depth + 1)
    for r in roots:
        lines.append(""); lines.append(f"trace {r['trace_id']}")
        walk(r, "", True, 0)
    meta = [json.loads(l) for l in (OUT / "server_meta_seen.jsonl").read_text().splitlines()]
    lines.append(""); lines.append("params._meta.traceparent as the server received it -> matching host span:")
    for m in meta:
        tp = m["_meta"].get("traceparent", ""); _, tid, sid, flags = tp.split("-")
        host_span = next((s for s in spans.values() if s["span_id"].endswith(sid)), None)
        lines.append(f"  {m['method']:<15} {str(m['name'] or ''):<12} {tp}  -> {host_span['name'] if host_span else 'NOT FOUND'}")

    def strip(sp):
        return {k: (v if k != "children" else [strip(c) for c in v]) for k, v in sp.items() if k not in ("label",)}
    (OUT / "trace.json").write_text(json.dumps([strip(r) for r in roots], indent=1))
    (OUT / "trace_tree.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
