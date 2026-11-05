"""Kill test. Three copies of the Fernhill server behind one load balancer; one client makes N tool calls;
after call K we kill one copy. Usage: run_kill.py SPEC(old|new) LB(rr|sticky) N K [GAP]
Optional env: KILL_SERVER / KILL_CLIENT (file names in this folder) and KILL_TAG (output name) for extra cells.
Writes data/m09/<spec>_<lb>.jsonl (one line per call) and <spec>_<lb>_lb.jsonl (one line per HTTP request)."""
import json, os, signal, socket, subprocess, sys, time
from pathlib import Path

SPEC, LB, N, K = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
GAP = float(sys.argv[5]) if len(sys.argv) > 5 else 0.15
HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m09"
PY = {"old": CODE / ".venv-old/bin/python", "new": CODE / ".venv-new/bin/python"}
PORTS, LBPORT = [8121, 8122, 8123], 8120
tag = os.environ.get("KILL_TAG", f"{SPEC}_{LB}")
SERVER = os.environ.get("KILL_SERVER", f"server_{SPEC}.py"); CLIENT = os.environ.get("KILL_CLIENT", f"client_{SPEC}.py"); lblog = DATA / f"{tag}_lb.jsonl"; lblog.unlink(missing_ok=True)

def wait_port(p, t=15):
    end = time.time() + t
    while time.time() < end:
        try: socket.create_connection(("127.0.0.1", p), 0.2).close(); return
        except OSError: time.sleep(0.1)
    raise SystemExit(f"port {p} did not open")

copies = [subprocess.Popen([PY[SPEC], HERE / SERVER, str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for p in PORTS]
for p in PORTS: wait_port(p)
time.sleep(0.5)
assert all(c.poll() is None for c in copies), "a copy did not start (port in use?)"
lb = subprocess.Popen([PY["new"], HERE / "lb.py", LB, str(LBPORT), lblog, *map(str, PORTS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(LBPORT)
cli = subprocess.Popen([PY[SPEC], HERE / CLIENT, f"http://127.0.0.1:{LBPORT}/mcp", str(N), str(GAP)],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
rows, killed = [], None
for line in cli.stdout:
    line = line.rstrip(); print(line, flush=True)
    if not line.startswith("CALL"): rows.append({"event": line}); continue
    _, i, st, ms, *msg = line.split(" ", 4); i = int(i)
    rows.append({"call": i, "ok": st == "ok", "ms": float(ms), "msg": msg[0] if msg else ""})
    if i == K and killed is None:
        # kill the copy that served the most recent tool call (for sticky: the pinned copy)
        last = [json.loads(l) for l in open(lblog)]
        served = [r["copy"] for r in last if r.get("method") == "tools/call" and r.get("copy") is not None]
        killed = served[-1] if served else 1
        copies[killed].send_signal(signal.SIGKILL); copies[killed].wait()
        rows.append({"event": f"KILLED copy {killed} after call {K}"}); print(f"*** KILLED copy {killed}", flush=True)
cli.wait()
for p in copies + [lb]:
    if p.poll() is None: p.terminate()
for p in copies + [lb]:
    try: p.wait(5)
    except Exception: p.kill()
ok = sum(1 for r in rows if r.get("ok")); calls = sum(1 for r in rows if "call" in r)
summary = {"spec": SPEC, "lb": LB, "server": SERVER, "client": CLIENT, "calls": calls, "ok": ok, "failed": calls - ok, "killed_copy": killed, "kill_after": K}
(DATA / f"{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in rows + [{"summary": summary}]) + "\n")
print("SUMMARY", json.dumps(summary))
