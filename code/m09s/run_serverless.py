"""Serverless model runs (see funchost.py). Usage: run_serverless.py CELL [N]
CELL: new_plain | warm_new_plain | old_stateless_plain | old_stateful_plain | old_stateful_reinit | mrtr_ephemeral | mrtr_shared
Writes data/m09s/<cell>.jsonl (calls) and <cell>_host.jsonl (one line per HTTP request, with cold_ms)."""
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
CELL = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m09s"
OLD, NEW = str(CODE / ".venv-old/bin/python"), str(CODE / ".venv-new/bin/python"); M9, M7 = CODE / "m09", CODE / "m07"
HOST, DIRECT = 8140, 8141
hostlog = DATA / f"{CELL}_host.jsonl"; hostlog.unlink(missing_ok=True)
env = {**os.environ, "FERNHILL_STATE_KEY": secrets.token_hex(32)}
def wait(p):
    for _ in range(200):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)
    raise SystemExit(f"port {p} did not open")
SERVERS = {"new_plain": [NEW, M9 / "server_new.py", "PORT"], "old_stateless_plain": [OLD, M9 / "server_old_stateless.py", "PORT"],
           "old_stateful_plain": [OLD, M9 / "server_old.py", "PORT"], "old_stateful_reinit": [OLD, M9 / "server_old.py", "PORT"],
           "mrtr_ephemeral": [NEW, M7 / "server_refund.py", "PORT", "ephemeral"], "mrtr_shared": [NEW, M7 / "server_refund.py", "PORT", "shared"]}
CLIENTS = {"new_plain": [NEW, M9 / "client_new.py"], "warm_new_plain": [NEW, M9 / "client_new.py"], "old_stateless_plain": [OLD, M9 / "client_old.py"],
           "old_stateful_plain": [OLD, M9 / "client_old.py"], "old_stateful_reinit": [OLD, M9 / "client_old_reinit.py"]}
procs = []
if CELL == "warm_new_plain":      # baseline: one long-lived process, no function host
    procs.append(subprocess.Popen([NEW, M9 / "server_new.py", str(DIRECT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)); wait(DIRECT)
    url = f"http://127.0.0.1:{DIRECT}/mcp"
else:
    procs.append(subprocess.Popen([NEW, HERE / "funchost.py", str(HOST), hostlog, "--", *map(str, SERVERS[CELL])], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)); wait(HOST)
    url = f"http://127.0.0.1:{HOST}/mcp"
rows = []
if CELL.startswith("mrtr"):
    for t in range(N):
        out = subprocess.run([NEW, M7 / "two_rounds.py", url], capture_output=True, text=True, timeout=120).stdout
        rounds = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        b = rounds[-1]["body"] if rounds else {}
        ok = "result" in b and b["result"].get("resultType") == "complete" and not b["result"].get("isError")
        rows.append({"trial": t, "rounds": len(rounds), "ok": ok, "error": None if ok else (b.get("error") or b.get("result", {}).get("content"))})
else:
    out = subprocess.run([*map(str, CLIENTS[CELL]), url, str(N), "0.15"], capture_output=True, text=True, timeout=600).stdout
    for line in out.splitlines():
        if line.startswith("CALL"):
            _, i, st, ms, *msg = line.split(" ", 4); rows.append({"call": int(i), "ok": st == "ok", "ms": float(ms), "msg": msg[0] if msg else ""})
        else: rows.append({"event": line})
for p in procs: p.terminate()
for p in procs:
    try: p.wait(10)
    except Exception: p.kill()
calls = [r for r in rows if "call" in r or "trial" in r]; ok = sum(1 for r in calls if r.get("ok"))
reqs = [json.loads(l) for l in open(hostlog)] if hostlog.exists() else []
ms = sorted(r["ms"] for r in calls if "ms" in r and r.get("ok"))
cold = sorted(r["cold_ms"] for r in reqs)
summary = {"cell": CELL, "calls": len(calls), "ok": ok, "http_requests": len(reqs),
           "median_call_ms": ms[len(ms) // 2] if ms else None, "median_cold_ms": cold[len(cold) // 2] if cold else None,
           "methods": sorted({r["method"] for r in reqs})}
(DATA / f"{CELL}.jsonl").write_text("\n".join(json.dumps(r) for r in rows + [{"summary": summary}]) + "\n")
print("SUMMARY", json.dumps(summary))
for r in rows:
    if not r.get("ok") and ("call" in r or "trial" in r): print("  first failure:", json.dumps(r)[:220]); break
