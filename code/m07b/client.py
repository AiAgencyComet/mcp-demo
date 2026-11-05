"""A raw MCP client (httpx, no SDK) that drives the Fernhill export as a task. It prints every message.
Usage: client.py URL RUN OUTDIR
RUN: discover | sync | basic | cancel | input | nocap | toolerror | errors | owner_dies | trial
Writes OUTDIR/<RUN>.txt (transcript; not for `trial`) and appends every message to OUTDIR/<JSONL>
(env FERNHILL_JSONL, default messages.jsonl). owner_dies reads env FERNHILL_PIDS="A=pid,B=pid"."""
import json, os, signal, sys, time, uuid
import httpx

URL, RUN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PV, TASKS = "2026-07-28", "io.modelcontextprotocol/tasks"
TERMINAL = {"completed", "failed", "cancelled"}
JSONL = open(os.path.join(OUT, os.environ.get("FERNHILL_JSONL", "messages.jsonl")), "a", buffering=1)
QUIET = RUN == "trial"

class Wire:
    def __init__(self):
        self.t0, self.seq, self.lines, self.seen, self.interval_ms = time.time(), 0, [], set(), 2000
        self.http = httpx.Client(timeout=120)

    def say(self, text=""):
        self.lines.append(text)
        if not QUIET: print(text, flush=True)

    def _short(self, msg: dict) -> str:
        """Compact JSON. A `_meta` object that this transcript already showed prints as "(same as above)"."""
        m = json.loads(json.dumps(msg))
        holder = m.get("params") or m.get("result") or {}
        if isinstance(holder, dict) and "_meta" in holder:
            key = json.dumps(holder["_meta"], sort_keys=True)
            if key in self.seen: holder["_meta"] = "(same as above)"
            self.seen.add(key)
        return json.dumps(m, ensure_ascii=False)

    def send(self, method, params=None, *, name=None, tasks_cap=True, note=None):
        self.seq += 1
        caps = {"extensions": {TASKS: {}}} if tasks_cap else {}
        meta = {"io.modelcontextprotocol/protocolVersion": PV, "io.modelcontextprotocol/clientCapabilities": caps,
                "io.modelcontextprotocol/clientInfo": {"name": "fernhill-raw", "version": "1"}}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PV, "Mcp-Method": method}
        if name: headers["Mcp-Name"] = name
        body = {"jsonrpc": "2.0", "id": self.seq, "method": method, "params": {**(params or {}), "_meta": meta}}
        t = time.time() - self.t0
        routing = {k: v for k, v in headers.items() if k.lower().startswith("mcp")}
        JSONL.write(json.dumps({"run": RUN, "seq": self.seq, "t": round(t, 3), "dir": "client->server", "method": method,
                                "headers": routing, "body": body, "note": note}) + "\n")
        self.say(f"[{t:6.2f}s] -> {method}" + (f"   Mcp-Name: {name}" if name else "") + (f"   ({note})" if note else ""))
        self.say("          " + self._short(body))
        start = time.time()
        r = self.http.post(URL, headers=headers, json=body)
        ms, reply, copy = round((time.time() - start) * 1000, 1), r.json(), r.headers.get("x-copy")
        t2 = time.time() - self.t0
        JSONL.write(json.dumps({"run": RUN, "seq": self.seq, "t": round(t2, 3), "dir": "server->client", "method": method,
                                "http": r.status_code, "copy": copy, "ms": ms, "body": reply}) + "\n")
        self.say(f"[{t2:6.2f}s] <- HTTP {r.status_code} from copy {copy} ({ms} ms)")
        self.say("          " + self._short(reply))
        self.interval_ms = (reply.get("result") or {}).get("pollIntervalMs", self.interval_ms)   # the latest hint
        return reply, copy

    def poll(self, task_id, *, until=TERMINAL, max_polls=200, stats=None):
        """tasks/get until the status is in `until`. Honors pollIntervalMs (spec: clients SHOULD)."""
        for _ in range(max_polls):
            reply, copy = self.send("tasks/get", {"taskId": task_id}, name=task_id)
            if stats is not None: stats.append({"copy": copy, "ok": "result" in reply,
                                                "status": reply.get("result", {}).get("status"),
                                                "error": reply.get("error", {}).get("message")})
            res = reply.get("result")
            if res and res["status"] in until: return reply
            if res is None and stats is None: return reply      # an error: a real client stops here
            time.sleep(self.interval_ms / 1000)
        return reply

    def save(self, title):
        if not QUIET:
            head = [f"# m07b · {RUN} · {title}", f"# URL {URL} · spec {PV} · Tasks extension {TASKS} · raw httpx client, no SDK",
                    "# Each message is shown once in full; a repeated _meta object prints as \"(same as above)\".",
                    "# Full, unshortened bodies: data/m07b/messages.jsonl", ""]
            open(os.path.join(OUT, f"{RUN}.txt"), "w").write("\n".join(head + self.lines) + "\n")

def export(w, days, **kw):
    return w.send("tools/call", {"name": "export_sales_report", "arguments": {"days": days}}, name="export_sales_report", **kw)

w = Wire()
if RUN == "discover":
    w.send("server/discover")
    reply, _ = w.send("tools/list")
    w.save("server/discover advertises the extension; tools/list has no per-tool task flag")

elif RUN == "sync":
    export(w, 3, note="3 days: short job")
    w.save("days=3: the server decides NOT to make a task and returns the normal CallToolResult")

elif RUN == "basic":
    reply, owner = export(w, 20, note="20 days: long job")
    task_id = reply["result"]["taskId"]
    stats = []
    final = w.poll(task_id, stats=stats)
    copies = {c: sum(1 for s in stats if s["copy"] == c) for c in sorted({s["copy"] for s in stats})}
    w.say(f"\n# summary: task created on copy {owner}; {len(stats)} polls answered by {copies}; "
          f"all ok: {all(s['ok'] for s in stats)}; final status {final['result']['status']}; wall {time.time() - w.t0:.1f} s")
    w.save("days=20 runs as a task; polls go round robin to both copies; the result arrives in tasks/get")

elif RUN == "cancel":
    reply, owner = export(w, 60, note="60 days: about 60 s of work")
    task_id = reply["result"]["taskId"]
    for k in range(5):        # 3 polls; then (round robin, 2 copies) poll until the owner answered last,
        time.sleep(w.interval_ms / 1000)        # so that the cancel lands on the OTHER copy
        reply, last = w.send("tasks/get", {"taskId": task_id}, name=task_id)
        if k >= 2 and last == owner: break
    _, cancel_copy = w.send("tasks/cancel", {"taskId": task_id}, name=task_id,
                            note=f"the person stops the export; the worker runs on copy {owner}")
    t_cancel = time.time()
    final = w.poll(task_id)
    t_seen = time.time()
    time.sleep(3)
    again, _ = w.send("tasks/get", {"taskId": task_id}, name=task_id, note="3 s later: a terminal status does not change")
    w.say(f"\n# summary: worker on copy {owner}; tasks/cancel answered by copy {cancel_copy}; status "
          f"{final['result']['status']} seen {t_seen - t_cancel:.1f} s after the ack; "
          f"lastUpdatedAt unchanged 3 s later: {again['result']['lastUpdatedAt'] == final['result']['lastUpdatedAt']}")
    w.save("days=60 is cancelled after 3 polls; the cancel lands on any copy, the worker's copy reads the flag")

elif RUN == "input":
    reply, owner = export(w, 30, note="30 days: day 24 has orders with no price")
    task_id = reply["result"]["taskId"]
    asked = w.poll(task_id, until=TERMINAL | {"input_required"})
    key = next(iter(asked["result"]["inputRequests"]))
    time.sleep(w.interval_ms / 1000)
    w.send("tasks/get", {"taskId": task_id}, name=task_id, note="poll again before answering: the same key comes back")
    w.send("tasks/update", {"taskId": task_id, "inputResponses": {"not-a-key": {"action": "accept", "content": {"skip": True}}}},
           name=task_id, note="on purpose: a key the server never asked for")
    w.send("tasks/get", {"taskId": task_id}, name=task_id, note="still input_required: the wrong key was ignored")
    w.send("tasks/update", {"taskId": task_id, "inputResponses": {key: {"action": "accept", "content": {"skip": True}}}},
           name=task_id, note="the person says: skip them")
    final = w.poll(task_id)
    w.say(f"\n# summary: question key {key}; final status {final['result']['status']}; "
          f"skipped {final['result']['result']['structuredContent']['skipped_orders']}; wall {time.time() - w.t0:.1f} s")
    w.save("mid-task question: input_required -> tasks/update -> working -> completed")

elif RUN == "nocap":
    export(w, 20, tasks_cap=False, note="this client does NOT declare the Tasks extension")
    export(w, 3, tasks_cap=False, note="same client, short job")
    w.save("a client without the extension: a long job gets -32021, a short job still works")

elif RUN == "toolerror":
    reply, _ = export(w, 400, note="400 days: the tool will refuse")
    w.poll(reply["result"]["taskId"])
    w.save("a tool error inside a task: status is completed (not failed) and result.isError is true")

elif RUN == "errors":
    reply, _ = export(w, 6, note="6 days: a task to test against")
    task_id = reply["result"]["taskId"]
    w.send("tasks/get", {"taskId": task_id}, name=task_id, tasks_cap=False, note="no Tasks extension in _meta")
    w.send("tasks/get", {"taskId": task_id}, name="export_sales_report", note="Mcp-Name is not the taskId")
    fake = str(uuid.uuid4())
    w.send("tasks/get", {"taskId": fake}, name=fake, note="a taskId that does not exist")
    w.send("tasks/result", {"taskId": task_id}, name=task_id, note="old 2025-11-25 method")
    w.send("tasks/list", {}, note="old 2025-11-25 method")
    final = w.poll(task_id)
    w.send("tasks/cancel", {"taskId": task_id}, name=task_id, note="cancel a task that is already completed")
    w.send("tasks/get", {"taskId": task_id}, name=task_id, note="still completed")
    w.send("tools/call", {"name": "export_sales_report", "arguments": {"days": 3}, "task": {"ttl": 60000}},
           name="export_sales_report", note="old per-request `task` parameter: the server must ignore it")
    w.save("protocol errors and removed methods")

elif RUN == "owner_dies":
    pids = dict(p.split("=") for p in os.environ["FERNHILL_PIDS"].split(","))
    reply, owner = export(w, 20, note="20 days")
    task_id = reply["result"]["taskId"]
    for _ in range(2):
        time.sleep(2); w.send("tasks/get", {"taskId": task_id}, name=task_id)
    os.kill(int(pids[owner]), signal.SIGKILL)
    w.say(f"\n# ---- the client side of this demo kills copy {owner} (pid {pids[owner]}) with SIGKILL: the worker dies with it ----\n")
    seen = []
    for _ in range(5):
        time.sleep(2)
        r, c = w.send("tasks/get", {"taskId": task_id}, name=task_id)
        seen.append(r["result"]["lastUpdatedAt"] if "result" in r else r.get("error"))
    w.say(f"\n# summary: worker copy {owner} killed; 5 more polls (10 s) all answered; lastUpdatedAt values: {sorted(set(map(str, seen)))}")
    w.save("the copy that runs the worker dies: the state survives, the work does not")

elif RUN == "trial":
    reply, owner = export(w, 12)
    stats = []
    w.poll(reply["result"]["taskId"], stats=stats, max_polls=40)
    print(json.dumps({"owner": owner, "polls": len(stats), "ok": sum(s["ok"] for s in stats),
                      "errors": sorted({s["error"] for s in stats if s["error"]}),
                      "by_copy": {c: [sum(1 for s in stats if s["copy"] == c and s["ok"]), sum(1 for s in stats if s["copy"] == c)]
                                  for c in sorted({s["copy"] for s in stats})},
                      "completed": any(s["status"] == "completed" for s in stats),
                      "first_error_poll": next((i + 1 for i, s in enumerate(stats) if not s["ok"]), None)}))
