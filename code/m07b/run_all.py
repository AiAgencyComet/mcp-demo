"""Run the m07b Tasks demos and save the data. Usage: run_all.py main|trials|all
main    2 copies with a shared sqlite store behind a round-robin load balancer; 1 s per day; pollIntervalMs 2000
trials  5 trials each of shared+rr, memory+rr, memory+affinity; 0.25 s per day; pollIntervalMs 250
Writes data/m07b/. Local only (127.0.0.1). Stops every process it starts."""
import json, os, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent; CODE = HERE.parent; DATA = CODE.parent / "data" / "m07b"
PY = str(CODE / ".venv-new/bin/python"); LBP, PORTS = 8180, {"A": 8181, "B": 8182}
RUN = HERE / "run"; RUN.mkdir(exist_ok=True); DATA.mkdir(parents=True, exist_ok=True)
WHAT = sys.argv[1] if len(sys.argv) > 1 else "all"

def busy(p):
    try: socket.create_connection(("127.0.0.1", p), .2).close(); return True
    except OSError: return False

def wait(p):
    for _ in range(150):
        if busy(p): return
        time.sleep(.1)
    raise SystemExit(f"port {p} did not open")

class Stack:
    def __init__(self, store, lb_mode, step_s, poll_ms, logdir, tag):
        for p in [LBP, *PORTS.values()]:
            if busy(p): raise SystemExit(f"port {p} is in use; stop that process first")
        db = RUN / "tasks.db"
        for f in RUN.glob("tasks.db*"): f.unlink()
        env = {**os.environ, "FERNHILL_STEP_S": str(step_s), "FERNHILL_POLL_MS": str(poll_ms)}
        self.procs, self.pids = [], {}
        for name, port in PORTS.items():
            err = open(logdir / f"{tag}server_{name}.log", "w")
            p = subprocess.Popen([PY, "server.py", str(port), name, store, str(db)], cwd=HERE, env=env,
                                 stdout=subprocess.DEVNULL, stderr=err)
            self.procs.append(p); self.pids[name] = p.pid
            wait(port)                       # one at a time: the first copy creates the sqlite file
        lblog = logdir / f"{tag}lb.jsonl"; lblog.unlink(missing_ok=True)
        self.procs.append(subprocess.Popen([PY, "lb.py", lb_mode, str(LBP), str(lblog), *[f"{n}={p}" for n, p in PORTS.items()]],
                                           cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(LBP); time.sleep(0.3)

    def client(self, run, jsonl="messages.jsonl"):
        env = {**os.environ, "FERNHILL_PIDS": ",".join(f"{n}={p}" for n, p in self.pids.items()), "FERNHILL_JSONL": jsonl}
        return subprocess.run([PY, "client.py", f"http://127.0.0.1:{LBP}/mcp", run, str(DATA)], cwd=HERE, env=env,
                              capture_output=True, text=True, timeout=300)

    def stop(self):
        for p in self.procs:
            if p.poll() is None: p.terminate()
        for p in self.procs:
            try: p.wait(10)
            except subprocess.TimeoutExpired: p.kill(); p.wait()

if WHAT in ("main", "all"):
    (DATA / "messages.jsonl").unlink(missing_ok=True)
    s = Stack("shared", "rr", 1.0, 2000, DATA, "")
    try:
        for run in ["discover", "sync", "basic", "cancel", "input", "nocap", "toolerror", "errors", "owner_dies"]:
            out = s.client(run)
            print(f"== {run}: exit {out.returncode}", (out.stderr[-800:] if out.returncode else ""))
            tail = [l for l in out.stdout.splitlines() if l.startswith("# summary")]
            if tail: print("  ", tail[-1])
    finally:
        s.stop()

if WHAT in ("trials", "all"):
    (DATA / "trials_messages.jsonl").unlink(missing_ok=True)
    rows = []
    for store, lb in [("shared", "rr"), ("memory", "rr"), ("memory", "affinity")]:
        s = Stack(store, lb, 0.25, 250, RUN, f"trials_{store}_{lb}_")
        try:
            for t in range(5):
                out = s.client("trial", jsonl="trials_messages.jsonl")
                r = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else {"error": out.stderr[-300:]}
                rows.append({"store": store, "lb": lb, "trial": t, **r}); print(rows[-1])
        finally:
            s.stop()
    (DATA / "trials.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    lines = ["config            polls answered   result reached (client polls on)   result reached (client stops at 1st error)   1st error at poll   errors seen"]
    for store, lb in [("shared", "rr"), ("memory", "rr"), ("memory", "affinity")]:
        g = [r for r in rows if r["store"] == store and r["lb"] == lb]
        ok, polls, done = sum(r["ok"] for r in g), sum(r["polls"] for r in g), sum(r["completed"] for r in g)
        errs = sorted({e for r in g for e in r["errors"]})
        strict = sum(r["completed"] and r["first_error_poll"] is None for r in g)
        firsts = sorted({r["first_error_poll"] for r in g if r["first_error_poll"]})
        lines.append(f"{store}+{lb:<10} {ok:>4}/{polls:<4} ({100 * ok / polls:5.1f}%)   {done}/{len(g)} trials"
                     f"                         {strict}/{len(g)} trials                                  {firsts or '-'}                 {errs}")
    (DATA / "trials.txt").write_text("# m07b trials: export_sales_report(days=12), 0.25 s per day, pollIntervalMs 250, "
                                     "2 copies, 5 trials per config\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))
