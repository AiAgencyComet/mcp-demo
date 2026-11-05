"""Multi round-trip behind a round-robin load balancer. Usage: run_mrtr.py ephemeral|shared TRIALS [tamper]
Writes data/m07/mrtr_<mode>[_tamper].jsonl"""
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
MODE, TRIALS = sys.argv[1], int(sys.argv[2]); TAMPER = len(sys.argv) > 3
HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m07"
PY = CODE / ".venv-new/bin/python"; PORTS, LBP = [8161, 8162, 8163], 8160
env = {**os.environ, "FERNHILL_STATE_KEY": secrets.token_hex(32)}
def wait(p):
    for _ in range(150):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)
procs = [subprocess.Popen([PY, HERE / "server_refund.py", str(p), MODE], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for p in PORTS]
for p in PORTS: wait(p)
time.sleep(0.5)
assert all(p.poll() is None for p in procs), "a copy did not start (port in use?)"
lblog = DATA / "lb.jsonl"; lblog.unlink(missing_ok=True)
procs.append(subprocess.Popen([PY, CODE / "m09/lb.py", "rr", str(LBP), lblog, *map(str, PORTS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)); wait(LBP)
rows = []
for t in range(TRIALS):
    out = subprocess.run([PY, HERE / "two_rounds.py", f"http://127.0.0.1:{LBP}/mcp"] + (["tamper"] if TAMPER else []), capture_output=True, text=True).stdout
    rounds = [json.loads(l) for l in out.splitlines()]
    if not rounds: rows.append({"trial": t, "ok": False, "error": "no JSON (copy down?)"}); continue
    r2 = rounds[-1]; b = r2["body"]
    ok = "result" in b and b["result"].get("resultType") == "complete" and not b["result"].get("isError")
    rows.append({"trial": t, "copy_round1": rounds[0]["copy"], "copy_round2": r2["copy"], "ok": ok,
                 "error": b.get("error") or (b.get("result", {}).get("content") if not ok else None)})
for p in procs: p.terminate()
for p in procs: p.wait(10)
tag = f"mrtr_{MODE}" + ("_tamper" if TAMPER else "")
(DATA / f"{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
same = sum(1 for r in rows if r["copy_round1"] == r["copy_round2"])
print(tag, "ok", sum(r["ok"] for r in rows), "/", len(rows), "| round 2 on the same copy:", same)
for r in rows[:3]: print("  ", r)
