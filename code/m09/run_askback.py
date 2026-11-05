"""Ask-back on the OLD spec: a refund that asks the person mid-call (elicitation), N calls, no copy is killed.
Usage: run_askback.py stateful|stateless rr|sticky|direct N   (direct = one copy, no load balancer)
Writes data/m09/askback_old_<mode>_<lb>.jsonl"""
import json, socket, subprocess, sys, time
from pathlib import Path
MODE, LB, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m09"
OLD, NEW = CODE / ".venv-old/bin/python", CODE / ".venv-new/bin/python"
PORTS, LBPORT = ([8131] if LB == "direct" else [8131, 8132, 8133]), 8130
tag = f"askback_old_{MODE}_{LB}"; lblog = DATA / f"{tag}_lb.jsonl"; lblog.unlink(missing_ok=True)
def wait(p):
    for _ in range(150):
        try: socket.create_connection(("127.0.0.1", p), .2).close(); return
        except OSError: time.sleep(.1)
    raise SystemExit(f"port {p} did not open")
procs = [subprocess.Popen([OLD, HERE / "server_old_refund.py", str(p), MODE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for p in PORTS]
for p in PORTS: wait(p)
time.sleep(0.5); assert all(p.poll() is None for p in procs), "a copy did not start"
url = f"http://127.0.0.1:{PORTS[0]}/mcp"
if LB != "direct":
    procs.append(subprocess.Popen([NEW, HERE / "lb.py", LB, str(LBPORT), lblog, *map(str, PORTS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wait(LBPORT); url = f"http://127.0.0.1:{LBPORT}/mcp"
out = subprocess.run([OLD, HERE / "client_old_refund.py", url, str(N)], capture_output=True, text=True, timeout=300).stdout
rows = []
for line in out.splitlines():
    print(line)
    if line.startswith("CALL"):
        _, i, st, ms, *msg = line.split(" ", 4); rows.append({"call": int(i), "ok": st == "ok", "ms": float(ms), "msg": msg[0] if msg else ""})
    else: rows.append({"event": line})
for p in procs: p.terminate()
for p in procs:
    try: p.wait(5)
    except Exception: p.kill()
ok = sum(1 for r in rows if r.get("ok")); calls = sum(1 for r in rows if "call" in r)
summary = {"spec": "old", "mode": MODE, "lb": LB, "copies": len(PORTS), "calls": calls, "ok": ok}
(DATA / f"{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in rows + [{"summary": summary}]) + "\n")
print("SUMMARY", json.dumps(summary))
