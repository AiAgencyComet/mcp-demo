# m07b · Long jobs with the MCP Tasks extension · RESULTS

Runs: 2026-11-04 (local PST; the timestamps in the data are UTC, 2026-11-05T05:5x). Local only (127.0.0.1), invented data.
Stack: Python 3.12, `mcp` 2.3.0 (`code/.venv-new`), httpx, sqlite3; Claude Code 2.1.318 for the host probe (no model call).

## Sources read before building (exact text quoted below)

| What | URL |
|---|---|
| Tasks spec, 2026-07-28 (the normative text) | https://github.com/modelcontextprotocol/ext-tasks/blob/cc9aaac1047a9440b07486e38f37060bbebeef4c/specification/2026-07-28/tasks.md |
| Tasks schema, 2026-07-28 | https://github.com/modelcontextprotocol/ext-tasks/blob/cc9aaac1047a9440b07486e38f37060bbebeef4c/schema/2026-07-28/schema.ts |
| SEP-2663 (Status: Final, Extensions Track) | https://github.com/modelcontextprotocol/ext-tasks/blob/cc9aaac1047a9440b07486e38f37060bbebeef4c/seps/2663-tasks-extension.md · https://modelcontextprotocol.io/seps/2663-tasks-extension · PR https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2663 |
| Docs overview | https://modelcontextprotocol.io/extensions/tasks/overview |
| Extension support matrix (community-maintained) | https://modelcontextprotocol.io/extensions/client-matrix |
| Release post | https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ |

ext-tasks repo commit read: `cc9aaac` ("v0.2.3", 2026-11-04T22:09:51Z). Local copies: scratchpad only (not in the project).

## What was built (`code/m07b/`)

| File | Lines | Role |
|---|---|---|
| `tasks_ext.py` | 216 | A minimal Tasks extension for mcp 2.3.0, on the SDK's own extension framework (`mcp.server.extension.Extension`): `intercept_tool_call` returns `CreateTaskResult`; `MethodBinding`s serve `tasks/get`, `tasks/update`, `tasks/cancel`; `progress()` and `ask()` for the tool. Two stores: `SqliteTaskStore` (shared file) and `MemoryTaskStore` (one process, for the contrast). |
| `server.py` | 70 | Fernhill `export_sales_report(days)`: 1 s per day (env `FERNHILL_STEP_S`), progress per day, a mid-task question on 2026-10-12 (two invented orders with no price). Policy: `days > 5` runs as a task. |
| `lb.py` | 44 | Load balancer: `rr` (round robin) or `affinity` (routes `tasks/*` on `Mcp-Name` to the copy that created the task). Adds an `x-copy` header. |
| `client.py` | 190 | Raw client (httpx, no SDK). Prints every message; writes `data/m07b/<run>.txt` and `messages.jsonl`. |
| `run_all.py` | 90 | Starts 2 copies + LB, runs everything, stops every process. `run_all.py main` (~95 s), `run_all.py trials` (~60 s). |
| `host_probe.py` | 65 | Records what Claude Code sends to the server. Default: no model call. `--live` exists but was NOT run. |
| `shop.py` | 21 | Copy of `code/fernhill/shop.py` (unchanged original). |

SDK fit: the framework fits without patches. These SDK facts made it possible (read in `mcp/server/runner.py` and `mcp/server/extension.py`):
- `MethodBinding` docstring: "A new request method an extension serves, e.g. `tasks/get`."
- `runner._serialize`: "A modern-era extension `resultType` (outside the core vocabulary) marks a claimed shape owned by the extension that defined it: the per-version surface doesn't describe it, so the sieve applies to core results only." So a `tools/call` result with `"resultType": "task"` passes through unchanged.
- Same function: for "custom methods, extension methods, and empty results" the runner sets `"resultType": "complete"` if the handler did not.
- `mcp.server.mcpserver.require_client_extension(ctx, id)` raises `-32021` with `requiredCapabilities`.

One gap: the SDK checks `Mcp-Name` only for `NAME_BEARING_METHODS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}` (`mcp/shared/inbound.py`). `tasks/*` is not in it, so `tasks_ext.py` checks `Mcp-Name == params.taskId` itself (reads `ctx.request.headers`).

## Data files (`data/m07b/`)

`discover.txt sync.txt basic.txt cancel.txt input.txt nocap.txt toolerror.txt errors.txt owner_dies.txt` (transcripts; a repeated `_meta` prints as "(same as above)"), `messages.jsonl` (144 records, every message in full: `run, seq, t, dir, method, headers, body, http, copy, ms, note`; `t` = seconds from the start of that run), `lb.jsonl` (72 routing records), `server_A.log`, `server_B.log` (worker events, epoch seconds), `trials.txt`, `trials.jsonl`, `trials_messages.jsonl`, `host_probe.json`.

## Verified facts: what ran, what came back

Setup for all `main` runs: 2 copies (A=8181, B=8182) with one shared sqlite file, behind `lb.py rr` (8180). `pollIntervalMs` 2000.

**1. Negotiation.** `server/discover` (discover.txt) returned `"capabilities": {"extensions": {"io.modelcontextprotocol/tasks": {}}, ...}`. The client declares it per request in `params._meta["io.modelcontextprotocol/clientCapabilities"] = {"extensions": {"io.modelcontextprotocol/tasks": {}}}`.
Spec: "No extension-specific settings are currently defined; an empty object indicates support."

**2. No per-tool flag.** The `tools/list` entry has only the keys `description, inputSchema, name, outputSchema`. Spec (server-directed): "The server is the sole decider; clients do not signal task preference on the request itself."

**3. Same tool, two result shapes (server-directed).** `days=3` (sync.txt): one HTTP request held for 3,013 ms, normal result, `"resultType": "complete"`, `structuredContent` `{"days": 3, "orders": 166, "revenue": 643.4, ...}`. `days=20` (basic.txt): answer in 3.3 ms:
```json
{"resultType":"task","taskId":"81547ab4-47cb-4428-a9bb-b694d6f37dad","status":"working","statusMessage":"Queued.",
 "createdAt":"2026-11-05T05:53:05.041Z","lastUpdatedAt":"2026-11-05T05:53:05.041Z","ttlMs":3600000,"pollIntervalMs":2000}
```
The handle is flat (`Result & Task`), as the schema says: "This type is Result & Task (flat)."

**4. Durable creation, then any copy answers.** The task was created on copy B; the first `tasks/get` went to copy A 2 ms later (t=0.024 s) and returned `"status":"working","statusMessage":"Day 1 of 20: reading 2026-11-04 (0% done)"`.
Spec: "A server **MUST NOT** return `CreateTaskResult` until the task is durably created — that is, until a `tasks/get` for the returned `taskId` would resolve." (Our store commits the sqlite INSERT before the response.)

**5. Polling and progress.** basic.txt: 11 polls in 20.1 s (client honors `pollIntervalMs`), answered by A 6, B 5, all OK. Progress travels in `statusMessage` only. The `Task` type has no numeric progress field, and the spec says: "`notifications/progress` and `notifications/message` notifications **MUST NOT** be sent on the `subscriptions/listen` stream for a task, and are not supported on tasks in general in this specification."

**6. The result arrives inside `tasks/get`.** Last poll (t=20.146 s, copy A): `"status":"completed","statusMessage":"Report ready."` plus `"result": {"content":[...],"isError":false,"resultType":"complete","structuredContent":{"first_day":"2026-10-16","last_day":"2026-11-04","days":20,"orders":1160,"revenue":4624.8,"top_drink":"latte","skipped_orders":[]}}`. The inner `result` has the keys `content, isError, resultType, structuredContent`: the same as the direct `days=3` call minus its `_meta` serverInfo stamp (it passes through the SDK's own `tools/call` serializer, `mcp_types.methods.serialize_server_result`). Spec: "the server sends the final tool result inlined into the task object". The outer object has `"resultType": "complete"` too. Spec: "The `resultType` field **MUST** be set to `"complete"` on this object".

**7. Cancel lands on one copy, the worker on the other.** cancel.txt (`days=60`): worker on copy B; `tasks/cancel` went to copy A and got `{"resultType":"complete"}` (empty ack). Server logs:
```
1793858013.301 copy A pid 83615: tasks/cancel 13aa44b2-...: flag set (status was working)
1793858014.291 copy B pid 83616: task 13aa44b2-... stopped (cancel seen after: Day 9 of 60: reading 2026-10-27 (13% done))
```
The worker stopped 0.99 s after the flag (it checks once per day of work). The poll right after the ack (2 ms later) still said `"working"`; the next poll (2.0 s later) said `"status":"cancelled","statusMessage":"Cancelled by the client. Last step: Day 9 of 60: ..."`. 3 s later `lastUpdatedAt` was unchanged (`2026-11-05T05:53:34.289Z`).
Spec: "Cancellation is **cooperative**" · "the task's observable status **MAY** remain `working` ... after the ack" · lifecycle diagram note: "Terminal states: completed, failed, cancelled". Also: "The `notifications/cancelled` notification **MUST NOT** be used for task cancellation."

**8. Mid-task question: `input_required` → `tasks/update`.** input.txt (`days=30`, worker on copy A, both `tasks/update` calls went to copy B):
- t=24.1 s: `"status":"input_required"` with `"inputRequests":{"unpriced-2026-10-12":{"method":"elicitation/create","params":{"mode":"form","message":"2 orders on 2026-10-12 have no price (A-0917, A-0921). Skip them?","requestedSchema":{...}}}}`
- The next poll returned the same key again (spec: "the server includes the same request again ... the client is advised to deduplicate").
- `tasks/update` with a key the server never asked for (`not-a-key`): ack `{"resultType":"complete"}`, task still `input_required`. Log: `accepted [], ignored ['not-a-key']`. Spec: "A server **SHOULD** ignore any `inputResponses` responses mapped to a key that is not currently outstanding".
- `tasks/update` with `{"unpriced-2026-10-12":{"action":"accept","content":{"skip":true}}}`: ack. The poll 3 ms later still said `input_required` (eventually consistent ack, spec: "the server **MAY** accept the responses and return the ack before the task's observable status ... reflects them"). The poll 2 s later: `"working"`, "Day 25 of 30".
- Final: `completed`, `"skipped_orders":["A-0917","A-0921"]`, `"orders":1655,"revenue":6603.5`, 34.2 s wall.

**9. Client without the extension.** nocap.txt: `days=20` → HTTP 400
```json
{"code":-32021,"message":"Client did not declare required extension 'io.modelcontextprotocol/tasks'","data":{"requiredCapabilities":{"extensions":{"io.modelcontextprotocol/tasks":{}}}}}
```
`days=3` from the same client → normal result. Spec: "A server **MUST NOT** return `CreateTaskResult` to a client that did not include the extension capability on its request" and "If a server is unable to service a request ... without returning `CreateTaskResult`, the server **MUST** return an error with the code `-32021`".

**10. A tool error inside a task is `completed`, not `failed`.** toolerror.txt (`days=400`): `"status":"completed","statusMessage":"Tool returned an error."`, `result.isError: true`, text `"Error executing tool export_sales_report: days must be 1 to 90, not 400."` (the prefix comes from the SDK). Spec: "The `failed` status **MUST NOT** be used to represent non-JSON-RPC errors, such as a tool result that completed with `isError: true`."

**11. Protocol errors** (errors.txt):

| Request | HTTP | JSON-RPC error |
|---|---|---|
| `tasks/get` without the extension in `_meta` | 400 | `-32021` "Client did not declare required extension 'io.modelcontextprotocol/tasks'" |
| `tasks/get` with `Mcp-Name: export_sales_report` (not the taskId) | 400 | `-32020` "Mcp-Name header does not match params.taskId" (our check, see gap above) |
| `tasks/get` for a random UUID | 400 | `-32602` "Failed to retrieve task: Task not found" (spec example text) |
| `tasks/result` (2025-11-25 method) | 404 | `-32601` "Method not found", `data: "tasks/result"` |
| `tasks/list` (2025-11-25 method) | 404 | `-32601` "Method not found", `data: "tasks/list"` |
| `tasks/cancel` on a completed task | 200 | ack; next `tasks/get` still `completed` |
| `tools/call` with the old `"task": {"ttl": 60000}` param, `days=3` | 200 | normal result; the param is ignored |

Spec: "`tasks/result` is removed; clients calling it **MUST** receive `-32601` (Method Not Found)" and "The `task` parameter on `CallToolRequest` is removed; servers **MUST** ignore it" (SEP-2663, Backward Compatibility). The HTTP status codes (400/404) come from the SDK (`mcp/shared/inbound.py` maps `-32021` to 400).

**12. Where task state lives: measured** (trials.txt; `days=12`, 0.25 s per day, `pollIntervalMs` 250, 2 copies, 5 trials per row):

| Store + load balancer | `tasks/get` answered | Result reached, client keeps polling | Result reached, client stops at first error | First error |
|---|---|---|---|---|
| shared sqlite + round robin | 65/65 (100%) | 5/5 | 5/5 | none |
| in-process memory + round robin | 35/70 (50%) | 5/5 | **0/5** | poll 1, "Failed to retrieve task: Task not found" |
| in-process memory + `Mcp-Name` affinity | 65/65 (100%) | 5/5 | 5/5 | none |

With strict round robin and 2 copies the split is exactly 50%; the first poll always goes to the other copy, so a client that treats `-32602` as "task gone" loses every task. The affinity row is the spec's own design: "the client **MUST** set the `Mcp-Name` header to the value of `params.taskId`. This allows transport intermediaries and load balancers to route subsequent requests for the same task to the server instance holding its state, which is typically required for correctness."

**13. The copy that runs the work dies.** owner_dies.txt: worker on copy A; after 2 polls the harness sends SIGKILL to copy A. The LB marks A down; 5 more polls over 10 s all go to copy B and all succeed, but every one says `"status":"working","statusMessage":"Day 5 of 20: reading 2026-10-31 (20% done)"` with the same `lastUpdatedAt` `2026-11-05T05:54:29.053Z`. The state survived; the work did not. Nothing in the spec restarts it. The only backstop is the TTL: "if the task's observable status has not reflected the update after `createdAt` plus `ttlMs` has elapsed, the client **MAY** consider the task to no longer be usable" and "servers **MAY** mark a task as `failed` at any point after the TTL elapses".

**14. Claude Code declares the extension.** host_probe.json (Claude Code 2.1.318, `claude -p ... --mcp-config ... --strict-mcp-config`; `ANTHROPIC_BASE_URL` pointed at a closed local port, so no model call; no `tools/call` reached the server). Each of its 8 requests (`server/discover`, `subscriptions/listen`, `prompts/list`, `resources/list`, `tools/list`, ...) used protocol `2026-07-28` and carried
`"clientCapabilities": {"roots": {"listChanged": true}, "elicitation": {"form": {}, "url": {}}, "extensions": {"io.modelcontextprotocol/tasks": {}}}`, `clientInfo.name "claude-code"`.
This matches the matrix (fetched 2026-11-04): Tasks is ticked for Claude (web), Claude Code, MCPJam, Glean; not for Claude Desktop or VS Code.

## Exact names from the spec (for on-screen text)

- Extension ID: `io.modelcontextprotocol/tasks`. Methods: `tasks/get`, `tasks/update`, `tasks/cancel`. Notification: `notifications/tasks` (opt-in via `subscriptions/listen` with `notifications.taskIds`).
- Discriminator: `resultType: "task"` on `CreateTaskResult`; `resultType: "complete"` on `GetTaskResult`, `UpdateTaskResult`, `CancelTaskResult`.
- `Task` fields: `taskId`, `status`, `statusMessage?`, `createdAt`, `lastUpdatedAt`, `ttlMs` (int or null), `pollIntervalMs?`. Status-specific: `inputRequests` (input_required), `result` (completed), `error` (failed).
- Statuses: `working`, `input_required`, `completed`, `failed`, `cancelled` (last three terminal).
- `tasks/update` params: `taskId`, `inputResponses`. Supported methods today: "`tools/call`" only.
- Error codes: `-32602` invalid/unknown taskId, `-32603` internal, `-32021` missing required client capability.
- Removed vs 2025-11-25: `tasks/result`, `tasks/list`, the per-request `task` param, `tasks.requests.*` capabilities.
- Security: "Servers **MUST** generate [task IDs] with sufficient entropy" (we use `uuid4`); "Servers **MUST** perform authentication and authorization checks on each task-related request" (not done here: no auth in this module).

## What I could NOT confirm

- **Claude Code polling a real task end to end.** It declares the extension (fact 14), but seeing it handle a `CreateTaskResult` needs a model call. `code/m07b/host_probe.py --live` is ready (haiku, one tool allowed); NOT run, per "No Claude API needed".
- **Claude (web)** support: only from the community matrix; not tested. Claude Desktop: no tick in the matrix; not tested.
- **`notifications/tasks` via `subscriptions/listen`**: not implemented (the SDK has a `ListenHandler`; wiring `taskIds` into it was out of scope).
- **TTL expiry** (`-32602` "Task has expired") and **`failed`** (a JSON-RPC error during the work): both coded in `tasks_ext.py`, neither exercised.
- **Server-side `Mcp-Name` rejection for `tasks/*`**: the spec puts the MUST on the client. Rejecting a mismatch with `-32020` is our choice (code borrowed from the core header-mismatch error); a missing header is not rejected.
- **Other SDKs**: the official TypeScript package `@modelcontextprotocol/ext-tasks` 0.2.3 is requester (client) side; its README: "Call tools through generation-agnostic Tasks requester APIs. The package also provides 2025-11-25 Tasks receiver support". C# SDK server support only seen in a search snippet ("Wires the tasks/get, tasks/update, and tasks/cancel handlers from the store"); not checked. PyPI: `mcp` latest 2.3.0; `mcp-tasks`, `mcp-ext-tasks`, `ext-tasks`, `modelcontextprotocol-ext-tasks` return 404.
- **Two small spec text inconsistencies (not a behavior question):** the Task Creation section says "The client uses `task.taskId`" but the schema and every example are flat (`taskId` at the top level), and we followed the schema. SEP-2663's compatibility table names the protocol version `2026-06-30`, while the release is `2026-07-28`.

## Not covered in the tutorials we checked

Checked 2026-11-04: aaif.io (2026-08-28), getclaudeskills.com (2026-08-20), cruxdigits.nl (2026-09-01), plus the official overview. None runs more than one server copy or measures anything. Not found in any of them:
- **Where task state must live, measured:** in-process state loses 50% of polls behind round robin, and every task (0/5 reach the result) for a client that stops at the first error (fact 12). One third-party blog post (getclaudeskills.com, not an official source) says "any server instance behind a plain load balancer can answer a `tasks/get` for any task ID"; that holds only with shared state.
- **`Mcp-Name = taskId` exists for routing** (affinity LB, fact 12). aaif.io shows the header in a curl line but not why.
- **State is not work:** shared state survives a dead copy, but the job stops and stays `working` forever (fact 13). cruxdigits says state "lives in your database or job queue" but shows no failure.
- **Progress is `statusMessage` text only:** there is no numeric progress field, and `notifications/progress` is not supported on tasks (fact 5).
- **The acks are eventually consistent, observed:** a poll right after `tasks/cancel` or `tasks/update` still shows the old status (facts 7, 8).
- **A tool error is `completed` + `isError`, not `failed`** (fact 10). **`-32021`** is the answer for a client without the extension (fact 9).
- **The cancel and the answer can land on a copy that does not run the work** (facts 7, 8): the flag and the answer travel through the shared store.
- **Claude Code 2.1.318 sends `io.modelcontextprotocol/tasks` on every request** (fact 14).

## Re-run

```
cd code/m07b
../.venv-new/bin/python run_all.py main     # ~95 s; ports 8180-8182 must be free
../.venv-new/bin/python run_all.py trials   # ~60 s
../.venv-new/bin/python host_probe.py       # ~70 s; ports 8181, 8183; no model call
```
After each run: `pgrep -fl "server.py 818|lb.py"` printed nothing (all processes stopped).

## Added 2026-11-05 · live Claude Code probe (host_probe.py --live, ONE run, claude-haiku via `claude -p`, Claude Code 2.1.318)
data/m07b/host_probe_live.json. Requests seen: server/discover, subscriptions/listen, notifications/cancelled, prompts/list,
resources/list, tools/list, subscriptions/listen, tools/call, tools/call (export_sales_report, days 20). No tasks/get.
- server/discover carried clientCapabilities {"roots":{"listChanged":true},"elicitation":{"form":{},"url":{}},"extensions":{"io.modelcontextprotocol/tasks":{}}}
- BOTH tools/call requests carried {"roots":{"listChanged":true},"elicitation":{"form":{},"url":{}}} — NO tasks extension on the call.
- Our server requires the extension on the call (require_client_extension → -32021), so it refused; Claude retried once, then told
  the person the report needs "a client that declares that extension" and suggested a shorter window.
Lesson: in this Claude Code version a server-directed task never starts from tools/call. A Tasks server should fall back to a normal
(synchronous) result when the call does not declare the extension. Caveat: one run, one Claude Code version.
