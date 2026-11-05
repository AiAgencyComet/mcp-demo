"""A minimal Tasks extension (io.modelcontextprotocol/tasks) for the mcp 2.3.0 Python SDK.

Spec: https://github.com/modelcontextprotocol/ext-tasks/blob/main/specification/2026-07-28/tasks.md (SEP-2663)
mcp 2.3.0 has the extension framework (mcp.server.extension) but no Tasks extension. This file adds one:
  - intercept_tool_call  the server decides, per request, if a tools/call runs as a task
  - methods()            tasks/get, tasks/update, tasks/cancel
Task state lives in a store outside the request (SqliteTaskStore), so any server copy can answer.
MemoryTaskStore keeps state inside one process: it is here only to show what goes wrong.
"""
import asyncio, contextvars, json, sqlite3, uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from mcp_types import CallToolRequestParams, RequestParams
from mcp_types import methods as wire
from mcp_types.jsonrpc import HEADER_MISMATCH, INTERNAL_ERROR, INVALID_PARAMS
from mcp.server.extension import Extension, MethodBinding
from mcp.server.mcpserver import require_client_extension
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError

TASKS = "io.modelcontextprotocol/tasks"
TERMINAL = {"completed", "failed", "cancelled"}

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# ---------- the store: task state outside the request ----------

class SqliteTaskStore:
    """One row per task. The worker writes `doc`; tasks/update and tasks/cancel write the other columns."""
    def __init__(self, path: str):
        self.path = path
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, doc TEXT NOT NULL,
                          responses TEXT NOT NULL DEFAULT '{}', cancel_requested INTEGER NOT NULL DEFAULT 0)""")
    def _db(self):
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)
    def create(self, doc: dict) -> None:
        with self._db() as db:   # committed before the server sends CreateTaskResult
            db.execute("INSERT INTO tasks (task_id, doc) VALUES (?, ?)", (doc["taskId"], json.dumps(doc)))
    def get(self, task_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT doc FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def put(self, doc: dict) -> None:
        with self._db() as db:
            db.execute("UPDATE tasks SET doc = ? WHERE task_id = ?", (json.dumps(doc), doc["taskId"]))
    def request_cancel(self, task_id: str) -> None:
        with self._db() as db:
            db.execute("UPDATE tasks SET cancel_requested = 1 WHERE task_id = ?", (task_id,))
    def cancel_requested(self, task_id: str) -> bool:
        with self._db() as db:
            return bool(db.execute("SELECT cancel_requested FROM tasks WHERE task_id = ?", (task_id,)).fetchone()[0])
    def add_responses(self, task_id: str, responses: dict) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = json.loads(db.execute("SELECT responses FROM tasks WHERE task_id = ?", (task_id,)).fetchone()[0])
            db.execute("UPDATE tasks SET responses = ? WHERE task_id = ?", (json.dumps({**old, **responses}), task_id))
            db.execute("COMMIT")
    def responses(self, task_id: str) -> dict:
        with self._db() as db:
            return json.loads(db.execute("SELECT responses FROM tasks WHERE task_id = ?", (task_id,)).fetchone()[0])

class MemoryTaskStore:
    """The same interface, but the state is a dict inside this one process."""
    def __init__(self):
        self.rows: dict[str, dict] = {}
    def create(self, doc): self.rows[doc["taskId"]] = {"doc": dict(doc), "responses": {}, "cancel": False}
    def get(self, task_id): return dict(self.rows[task_id]["doc"]) if task_id in self.rows else None
    def put(self, doc): self.rows[doc["taskId"]]["doc"] = dict(doc)
    def request_cancel(self, task_id): self.rows[task_id]["cancel"] = True
    def cancel_requested(self, task_id): return self.rows[task_id]["cancel"]
    def add_responses(self, task_id, responses): self.rows[task_id]["responses"].update(responses)
    def responses(self, task_id): return dict(self.rows[task_id]["responses"])

# ---------- what a tool calls while it runs as a task ----------

_current: contextvars.ContextVar[tuple["TasksExtension", str] | None] = contextvars.ContextVar("task", default=None)

class TaskStopped(ToolError):
    """Raised inside the tool when the client cancelled the task."""

async def progress(message: str) -> None:
    """Report progress. In a task this sets `statusMessage` (the spec has no other progress field for tasks)."""
    if (cur := _current.get()) is None:
        return
    ext, task_id = cur
    if ext.store.cancel_requested(task_id):       # cooperative cancel: checked at each step
        ext.stopped.add(task_id)
        raise TaskStopped("cancelled")
    ext.write(task_id, status="working", statusMessage=message)

async def ask(key: str, message: str, schema: dict, poll_s: float = 0.5) -> dict:
    """Ask the client a question mid-task: status -> input_required, wait for tasks/update, status -> working."""
    if (cur := _current.get()) is None:
        raise ToolError("This question needs a task. Call again from a client that declares the Tasks extension.")
    ext, task_id = cur
    request = {"method": "elicitation/create", "params": {"mode": "form", "message": message, "requestedSchema": schema}}
    ext.write(task_id, status="input_required", statusMessage=message, inputRequests={key: request})
    while key not in (answers := ext.store.responses(task_id)):
        if ext.store.cancel_requested(task_id):
            ext.stopped.add(task_id)
            raise TaskStopped("cancelled")
        await asyncio.sleep(poll_s)
    doc = ext.store.get(task_id)
    doc.pop("inputRequests", None)
    doc["answeredKeys"] = doc.get("answeredKeys", []) + [key]   # internal; never sent (see _wire)
    ext.store.put(doc)
    ext.write(task_id, status="working", statusMessage="Answer received. Going on.")
    return answers[key]

# ---------- the extension ----------

class TaskIdParams(RequestParams):
    task_id: str

class UpdateParams(TaskIdParams):
    input_responses: dict[str, Any]

class TasksExtension(Extension):
    identifier = TASKS

    def __init__(self, store, runs_as_task: Callable[[str, dict], bool], *, ttl_ms=3_600_000, poll_interval_ms=2000,
                 log: Callable[[str], None] = lambda s: None):
        self.store, self.runs_as_task, self.ttl_ms, self.poll_ms, self.log = store, runs_as_task, ttl_ms, poll_interval_ms, log
        self.stopped: set[str] = set()
        self._workers: set[asyncio.Task] = set()

    def methods(self):
        return [MethodBinding("tasks/get", TaskIdParams, self._get),
                MethodBinding("tasks/update", UpdateParams, self._update),
                MethodBinding("tasks/cancel", TaskIdParams, self._cancel)]

    # tools/call: return a task handle instead of the result, when the server decides so
    async def intercept_tool_call(self, params: CallToolRequestParams, ctx, call_next):
        if not self.runs_as_task(params.name, params.arguments or {}):
            return await call_next(ctx)                    # short job: the normal CallToolResult
        require_client_extension(ctx, TASKS)               # -32021 if the client did not declare Tasks
        t = now()
        doc = {"taskId": str(uuid.uuid4()), "status": "working", "statusMessage": "Queued.",
               "createdAt": t, "lastUpdatedAt": t, "ttlMs": self.ttl_ms, "pollIntervalMs": self.poll_ms}
        self.store.create(doc)                             # durable before the response goes out
        worker = asyncio.create_task(self._run(doc["taskId"], ctx, call_next, ctx.protocol_version))
        self._workers.add(worker); worker.add_done_callback(self._workers.discard)
        self.log(f"created task {doc['taskId']} for {params.name}({params.arguments})")
        return {"resultType": "task", **doc}

    async def _run(self, task_id, ctx, call_next, version):
        _current.set((self, task_id))
        try:
            result = await call_next(ctx)                  # the real tool, through the SDK, after the response
            if task_id in self.stopped:
                last = self.store.get(task_id).get("statusMessage", "")
                self.write(task_id, status="cancelled", statusMessage=f"Cancelled by the client. Last step: {last}")
                self.log(f"task {task_id} stopped (cancel seen after: {last})")
                return
            dumped = result.model_dump(by_alias=True, mode="json", exclude_none=True) if hasattr(result, "model_dump") else result
            body = wire.serialize_server_result("tools/call", version, dumped)   # same shape as a direct tools/call
            msg = "Tool returned an error." if body.get("isError") else "Report ready."
            self.write(task_id, status="completed", statusMessage=msg, result=body)
            self.log(f"task {task_id} completed")
        except MCPError as e:                              # JSON-RPC error -> failed (isError results stay completed)
            self.write(task_id, status="failed", statusMessage=e.error.message, error=e.error.model_dump(exclude_none=True))
        except Exception as e:
            self.write(task_id, status="failed", statusMessage=str(e), error={"code": INTERNAL_ERROR, "message": str(e)})

    def write(self, task_id: str, **fields) -> None:
        doc = self.store.get(task_id)
        if doc["status"] in TERMINAL:                      # terminal states never change
            return
        if fields.get("status") != "input_required":
            doc.pop("inputRequests", None)
        doc.update(fields, lastUpdatedAt=now())
        self.store.put(doc)

    # ---------- tasks/get, tasks/update, tasks/cancel ----------

    def _load(self, ctx, task_id: str) -> dict:
        require_client_extension(ctx, TASKS)               # spec: -32021 for clients that did not declare Tasks
        headers = {k.lower(): v for k, v in (getattr(ctx.request, "headers", None) or {}).items()}  # the HTTP request
        if "mcp-name" in headers and headers["mcp-name"] != task_id:   # our check of the MUST on the client
            raise MCPError(code=HEADER_MISMATCH, message="Mcp-Name header does not match params.taskId")
        doc = self.store.get(task_id)
        if doc is None:
            raise MCPError(code=INVALID_PARAMS, message="Failed to retrieve task: Task not found")
        created = datetime.fromisoformat(doc["createdAt"].replace("Z", "+00:00"))
        if doc["ttlMs"] is not None and datetime.now(timezone.utc) > created + timedelta(milliseconds=doc["ttlMs"]):
            raise MCPError(code=INVALID_PARAMS, message="Failed to retrieve task: Task has expired")
        return doc

    @staticmethod
    def _wire(doc: dict) -> dict:
        return {"resultType": "complete", **{k: v for k, v in doc.items() if k != "answeredKeys"}}

    async def _get(self, ctx, params: TaskIdParams):
        return self._wire(self._load(ctx, params.task_id))

    async def _update(self, ctx, params: UpdateParams):
        doc = self._load(ctx, params.task_id)
        open_keys = set(doc.get("inputRequests", {})) - set(doc.get("answeredKeys", []))
        accepted = {k: v for k, v in params.input_responses.items() if k in open_keys}   # others: ignored (spec)
        if accepted:
            self.store.add_responses(params.task_id, accepted)
        self.log(f"tasks/update {params.task_id}: accepted {sorted(accepted)}, ignored {sorted(set(params.input_responses) - set(accepted))}")
        return {"resultType": "complete"}

    async def _cancel(self, ctx, params: TaskIdParams):
        doc = self._load(ctx, params.task_id)
        if doc["status"] in TERMINAL:                      # ack only: a terminal task does not change
            self.log(f"tasks/cancel {params.task_id}: nothing to do (status is {doc['status']})")
        else:
            self.store.request_cancel(params.task_id)      # a flag in the shared store; the worker's copy reads it
            self.log(f"tasks/cancel {params.task_id}: flag set (status was {doc['status']})")
        return {"resultType": "complete"}
