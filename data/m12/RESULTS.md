# Module 12 results: test, evaluate, ship (measured 2026-11-04/05, all local, nothing published)

Stack: `mcp` 2.3.0 (spec 2026-07-28), `anthropic` 2.5.0, `opentelemetry-sdk` 1.45.2, `pytest` 9.2.0 + anyio plugin 4.16.0,
`jsonschema` 4.26.0, `@anthropic-ai/mcpb` 2.1.2 (pinned, via `npx -y`), uv 0.11.6, Python 3.12 (`code/.venv-new`).
Model for every API call: `claude-haiku-5-5` ($0.10 / $0.50 per M tokens, from the claude-api skill model table).
Code: `code/m12/`. The Fernhill server in `code/fernhill/` was not changed; new releases are copies in `code/m12/releases/`.

**Money spent: $0.299** (eval $0.2982 for 1,152 cached responses + trace run $0.0006 for 3 calls). Budget was $2.

---

## 1. Unit tests (pytest, in-process client, no network, no model)

Run: `cd code/m12 && ../.venv-new/bin/python -m pytest -v` -> `data/m12/pytest.txt`
```
collected 26 items
tests/test_contract.py ....  tests/test_fernhill.py ..................  tests/test_v2_bad.py ....
============================== 26 passed in 0.47s ==============================
```
`tests/test_fernhill.py` (18 tests): tools/list names and shape, `place_order` schema (`required` = items, handoff;
`handoff.anyOf` = `#/$defs/Pickup`, `#/$defs/Delivery`; milk enum), good order, bad drink, bad size, schema violation,
unknown order, refund confirm / decline / no-capability, resources + template, missing resource, prompts, stdio smoke test
(the server started as a subprocess the way a host starts it).

Verified facts (each one is an assert that passes):
- Good order: `{"order_id": "A-1043", "total": 5.10, "status": "making"}` (large oat latte = 4.50 + 0.60).
- Bad drink -> `is_error: true`, text exactly: `Error executing tool place_order: 'mocha' is not on the menu. Call get_menu to see the menu.`
  (SDK prefixes the ToolError text with `Error executing tool <name>: `.)
- Missing required field -> `is_error: true` with the pydantic text `items.0.size  Field required` (a result, not an exception).
- `refund` input schema shows only `order_id`: the `answer` parameter (Resolve + Elicit) is hidden from the model.
- A client with no `elicitation_callback` cannot refund: `call_tool("refund")` RAISES `MCPError: Client did not declare the
  form elicitation capability required by resolver 'server:ask_person'` (not an `is_error` result).
- Confirm -> `{"result": "Refunded $7.50 for A-1042."}` and status `refunded`; decline -> `"The person stopped the refund."`, status stays `done`.
- Missing order resource `fernhill://orders/Z-9` raises `MCPError: Error creating resource from template fernhill://orders/Z-9`
  (the KeyError is hidden from the client).
- Extra argument `{"order_id": "A-1041", "include_items": true}` is SILENTLY IGNORED (no `additionalProperties: false` in the
  generated schema); wrong type `order_id: 1041` -> `is_error: true`.

Test-isolation trap (`data/m12/pytest_no_reset.txt`): `shop.ORDERS` is a module global and the next ID is `1041 + len(ORDERS)`.
With the reset fixture off (`M12_NO_RESET=1`) and a different test order: `2 failed, 2 passed` -
`{'order_id': 'A-1044'} != {'order_id': 'A-1043'}` and `assert 'refunded' == 'done'`. Fix: autouse fixture in `code/m12/conftest.py`.

The refactor PR (`releases/fernhill_v2_bad.py`) ships its own updated tests: `tests/test_v2_bad.py` 4 passed. Unit tests stay green
through every release in this module; they test the code, not the model's view of it.

---

## 2. Tool-choice eval with a release gate

Code: `code/m12/eval/run_eval.py`, cases `code/m12/eval/cases.py`. Raw responses: `data/m12/raw/<release>/<case>_r<rep>.json`
(+ `_tools_offered.json`). Per-release report: `data/m12/eval_<release>.txt` and `.json` (every row: pick, args, check, tokens).
- 36 hand-written manager requests (30 for Fernhill tools: 7 menu, 10 order, 7 status, 6 refund; 6 for other servers), x 3 reps.
- Model sees the release's tools from MCP `tools/list` (prefix `fernhill__`) + 5 distractor tools of other servers
  (`stock__check_stock`, `suppliers__create_purchase_order`, `staff__list_shifts`, `loyalty__get_points`, `catering__quote_event`) = 9 tools, ~1,700 input tokens.
- System: "You are the assistant of the manager of Fernhill Coffee. Do the request by calling exactly one tool. Do not ask questions."
  `tool_choice: auto`, `max_tokens` 600, thinking left at the model default.
- Score "choice" = first tool call is the labelled tool. Score "call" = that call RUN on the real release server (fresh shop state,
  confirm = yes) has the right effect: right items (drink+size, milk when said), right pickup name / delivery address, right order ID.
- Gate (fixed before the first run): FAIL if choice < 80%, or choice or call drops > 5 points vs the baseline release.
- Holdout set: 12 more requests written after the v1 run and before any v1.1 run (to test the fix on cases it was not tuned on).

| release (what changed) | choice | Fernhill choice | call right | no tool call | gate |
|---|---|---|---|---|---|
| v1 = code/fernhill as released | 92.6% | 91.1% | **67.8%** | 0 | PASS (baseline) |
| v1.1 fix (any-case drink/size, 3 better descriptions) | **100%** | 100% | **100%** | 0 | PASS vs v1 |
| v2 "bad" refactor of v1 (po_create, "Tool.", p1/p2) | 98.1% | 97.8% | 88.9% | 1 | **PASS vs v1** (not caught) |
| only renames (abl_names) | 92.6% | 91.1% | 66.7% | 1 | PASS vs v1 |
| only descriptions -> "Tool." (abl_docs) | 97.2% | 96.7% | 91.1% | 1 | PASS vs v1 |
| only fields -> p1.. (abl_fields) | 91.7% | 90.0% | 70.0% | 0 | PASS vs v1 |
| v2 refactor applied to v1.1 (v2_on_v1_1) | 97.2% | 96.7% | 93.3% | 2 | **FAIL vs v1.1** (call -6.7 pts) |
| docs PR: order_status/refund docstrings swapped (v1_2_swap) | **63.9%** | 56.7% | 56.7% | 16 | **FAIL vs v1.1** (-36.1 / -43.3 pts) |
| same, max_tokens 4000 (sensitivity) | 65.7% | 58.9% | 58.9% | 16 | FAIL vs v1.1 |
| docs PR: get_menu "Call this tool first, before any other Fernhill tool" (v1_2_first) | **65.7%** | 58.9% | 58.9% | 0 | **FAIL vs v1.1** (-34.3 / -41.1 pts) |
| holdout: v1 | 77.8% | 73.3% | 50.0% | 2 | FAIL (< 80%) |
| holdout: v1.1 | 100% | 100% | 90.0% | 0 | PASS vs v1 holdout |
Other-server requests: 100% kept in every release (no Fernhill tool ever grabbed "Order 20 cartons of oat milk from Green Valley Dairy").

What the eval found (verbatim from the reports):
1. **The released v1 server has a bug the unit tests did not see.** Haiku writes capitals: `{'drink': 'Latte', 'size': 'large'}`,
   `'Cold Brew'`, `'Espresso', 'size': 'Double'`. v1 matches case-sensitively: `call fail x3: order-01: is_error: Error executing tool
   place_order: 'Latte' is not on the menu.` Order calls right: 20% (group "order 90/20"). Tests were written in lower case by the author.
2. **The field name `drink` drops food.** "An oat cookie and a single espresso ..." -> `items [('espresso', 'single')]` (cookie gone);
   cookie orders were also the ones that went to `get_menu` first.
3. **"The person must confirm first." makes the model check first.** `wrong x5: fernhill__refund -> fernhill__order_status`.
   v1.1 text "The server asks the person to confirm, so call this tool at once." -> refund 100%.
4. **The brief's "bad release" did not regress on Haiku.** Renames alone and p1 fields alone = v1 level; removing descriptions
   IMPROVED v1 (97.2%), because v1's descriptions were the cause of findings 2 and 3. With 4 tools the model still reads the
   schema structure (`$defs` titles Item / Pickup / Delivery, `kind` const pickup/delivery, milk enum). Matches module 5 ("one clear signal is enough").
   Against the good v1.1 baseline the same refactor fails, but only on call effect (93.3% vs 100%: cookie sizes guessed as
   `'regular'`/`'standard'`, `p2` missing). Narrow margin: 6 of 90 Fernhill runs.
5. **Broken descriptions are what the gate catches.** Swapped docstrings: status 0%, refund 0%. The model follows the DESCRIPTION
   over the NAME: 18/18 refund requests called `order_status` (described as refund), 5 status requests called `refund`
   (args `{'order_id': 'A-1041'}` - the confirm step from module 7 is the only safety net). 16 status runs made no call; the model
   wrote e.g. "I didn't check order A-1042 because the order tools are mislabeled, and calling the wrong one could issue a refund."
   "Call this tool first": 30/30 order runs -> `get_menu` (`Ring up a large oat latte for pickup, name's Sam. -> [('fernhill__get_menu', {})]`).
6. Haiku 5.5 thinks by default (adaptive, `display` omitted = empty thinking text): thinking blocks in 33-87% of runs.
   With max_tokens 600, the swap release hit `stop_reason: max_tokens` 15 times (thinking only). At 4000: 0 cut-offs, same verdict.
   A cut-off can still carry a `tool_use` block with partial input: v1 order-05 r1 sent `{}` -> validation error. Host rule: never run a tool call when `stop_reason` is `max_tokens`.
7. Latency follows confusion: v1.1 avg 1,063 ms and 108 output tokens; swap 1,695 ms / 235 output tokens; v1 1,372 ms / 173.

Re-scoring is free: a second run reads `data/m12/raw/` (key = request + tools SHA); 1,152 cached files, re-scored with no new call (mtimes unchanged).
Caveats: one model (Haiku), 3 reps; requests written by one author; v1.1 fix was designed while looking at the main set
(holdout is the fair check: 100% / 90%; its one miss is real: "a cookie" -> `'cookie' is not on the menu`). Ablations and
v1_2_* are definition transforms of v1/v1.1 (the call runs on the v1/v1.1 server through a name/argument map); v1, v1.1 and v2_bad are real server files.

---

## 3. Tracing: one agent request across two processes (OpenTelemetry)

Code: `code/m12/trace/traced_agent.py` (host, starts the server on 127.0.0.1:8212 and stops it), `traced_server.py` (runs the
UNCHANGED `code/fernhill/server.py` with a tracer provider + one business span per tool + a `_meta` log), `tree.py`, `otel_setup.py`
(JSON-lines exporter, `SimpleSpanProcessor`). Output: `data/m12/trace/host_spans.jsonl`, `server_spans.jsonl`, `server_meta_seen.jsonl`,
`trace.json` (nested), `trace_tree.txt`, `agent_run.json`.
Question: "I want a large oat latte for pickup, name Sam. What is the total, and what is my order ID?" -> answer "The order ID is
**A-1043**, and the total is **$5.10**." 3 Claude calls, 2 tool calls (`get_menu`, then `place_order`), wall 3,744 ms.

```
22 spans from 2 processes, 2 traces, 6 server spans whose parent is a host span
[host]   invoke_agent fernhill-helper  (INTERNAL, 3727.6 ms)
[host]   ├─ MCP send server/discover  (CLIENT, 2.5 ms)
[server] │  └─ server/discover  (SERVER, 0.3 ms)
[host]   ├─ MCP send tools/list  (CLIENT, 1.4 ms)
[server] │  └─ tools/list  (SERVER, 0.2 ms)
[host]   ├─ anthropic.messages.create  (CLIENT, 1183.0 ms)  claude-haiku-5-5  in 1144 / out 97 tok (thinking 64)  stop tool_use
[host]   ├─ execute_tool fernhill__get_menu  (INTERNAL, 17.8 ms)
[host]   │  └─ MCP send tools/call get_menu  (CLIENT, 2.3 ms)
[server] │     └─ tools/call get_menu  (SERVER, 0.9 ms)
[server] │        └─ fernhill.get_menu  (INTERNAL, 0.0 ms)
[host]   ├─ anthropic.messages.create  (CLIENT, 923.5 ms)  ... in 1413 / out 118 tok (thinking 0)  stop tool_use
[host]   ├─ execute_tool fernhill__place_order  (INTERNAL, 7.3 ms)
[host]   │  └─ MCP send tools/call place_order  (CLIENT, 5.6 ms)
[server] │     └─ tools/call place_order  (SERVER, 1.6 ms)
[server] │        └─ fernhill.place_order  (INTERNAL, 0.1 ms)  id=A-1043  total=5.1
[host]   └─ anthropic.messages.create  (CLIENT, 1583.2 ms)  ... in 1563 / out 214 tok (thinking 114)  stop end_turn
```
`params._meta` as the server received it (`server_meta_seen.jsonl`), e.g. for place_order:
`{"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientInfo": {"name": "mcp", "version": "0.1.0"},
"io.modelcontextprotocol/clientCapabilities": {}, "traceparent": "00-4b0f5b07b4e69ae69ff5cc1fb9d528a7-135447b3e8311d32-03"}`
-> span id `135447b3e8311d32` = the host span `MCP send tools/call place_order`. All 6 traceparents match a host span.

Verified facts:
- Zero tracing code is needed in an MCP server or client on mcp 2.3.0: the SDK ships `OpenTelemetryMiddleware` ON by default
  (`mcp/server/lowlevel/server.py`: `self.middleware = [OpenTelemetryMiddleware()]`, "a no-op until an OTel exporter is installed")
  and the client dispatcher injects W3C context (`mcp/shared/jsonrpc_dispatcher.py`, "SEP-414: inject W3C trace context").
  Registering a `TracerProvider` is the whole setup. Span names: client `MCP send <method> <name>`, server `<method> <name>`;
  server attributes `mcp.method.name`, `mcp.protocol.version`, `jsonrpc.request.id`, `gen_ai.operation.name: execute_tool`, `gen_ai.tool.name`.
- Only `traceparent` is sent (no `tracestate`, no `baggage` - none was set). Flags are `03` (sampled + random trace-id flag), not `01`.
- The context travels ONLY in `params._meta` (the two processes share nothing else). The in-process `Client(server.mcp)` path
  "dispatches directly without JSON-RPC framing" (Client docstring), so the cross-process demo uses Streamable HTTP.
- Sync tools run on a worker thread (`anyio.to_thread.run_sync`), and the context still reaches them: `fernhill.place_order` nests under the server span.
- The Claude SDK (anthropic 2.5.0, `anthropic/_tracing.py`) also emits its own `anthropic.messages.create` CLIENT span with
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.reasoning.output_tokens`, `anthropic.message.stop_reason`,
  and injects `traceparent` into its HTTPS request. Default content mode `metadata_only` (no prompt text in spans).
- PRIVACY: that span carries `anthropic.organization.id` and `anthropic.workspace.id` by default, and the server exception event
  carries a stack trace with the local home path. `tree.py` redacts both in the saved files ("<org-id redacted>", `~/`). Redact before any screen.
- Tool error (`trace 0xc6e9...`, direct call with "mocha"): server span `tools/call place_order` STATUS=ERROR `error.type=tool_error`,
  business span `error.type=ToolError` + exception event; the host `MCP send tools/call` CLIENT span stays UNSET (a tool error is a
  result, not a JSON-RPC error). Watch errors on the server side or set the status yourself (traced_agent sets it on `execute_tool`).
- Time split: the model is 3,690 ms of 3,728 ms (99%); every MCP round trip is 1.4-5.6 ms on localhost.

---

## 4. Ship: desktop extension, registry entry, versioning (nothing published)

### 4a. `.mcpb` (Claude Desktop extension) - `code/m12/ship/mcpb/fernhill-coffee/`, built file `code/m12/ship/dist/fernhill-coffee-1.1.0.mcpb`
Ships v1.1.0 (the release that passed the gate). `manifest.json` (manifest_version 0.4): `server.type: "uv"`, `entry_point: server/server.py`,
`mcp_config: {"command": "uv", "args": ["run", "--directory", "${__dirname}", "server/server.py"]}` (shape from the upstream
`examples/hello-world-uv`), 4 tools listed, `compatibility.runtimes.python ">=3.12"`. `pyproject.toml` pins `mcp==2.3.0`; `uv.lock` (31 packages) packed too.
Outputs: `data/m12/ship/mcpb_validate_pack_info.txt`, `mcpb_pack_final.txt`, `mcpb_negative_unpack_sha.txt`, `mcpb_run_bundle.txt`.
- `mcpb validate manifest.json` -> `Manifest schema validation passes!` exit 0.
- Broken copy (no author, `server.type: "python3"`) -> `- author: Required` / `- server.type: Invalid enum value. Expected 'python' | 'node' | 'binary' | 'uv', received 'python3'`, exit 1.
- `mcpb pack` -> 5 files, package 45.4 kB, unpacked 134.8 kB; `mcpb info` -> `WARNING: Not signed` (we did not sign).
- `pack` prints `shasum: 1195ee5e...` = SHA-1 (`shasum -a 1` matches). The registry needs SHA-256: `dd688abd4107b5fd4b678e05575cf7ee9380d495505c6f2f0c33dad4f46ad70f`.
- `pack` excludes `.env*` by default but NOT `.venv/` or `__pycache__/` (list in `dist/node/files.js`) -> a `.mcpbignore` is required for Python.
- Unpacked and started the way a host does (`ship/run_bundle.py`, `${__dirname}` replaced): first ever start 2,153 ms (uv downloaded
  pydantic-core 2.0 MiB + cryptography 3.7 MiB, installed 28 packages), fresh folder with warm uv cache 1,305 ms, warm start 236-255 ms.
  uv creates `.venv` INSIDE the bundle folder. `place_order("Latte","Large")` -> `{"order_id": "A-1043", "total": 5.1}`.
- First build reported `serverInfo` `"fernhill "` (empty version: `MCPServer(version="")` default). Fixed in v1.1 with
  `MCPServer("fernhill", version="1.1.0", ...)`; rebuilt bundle reports `fernhill 1.1.0`.
- NOT tested: installing the `.mcpb` into Claude Desktop (UI step), signing (`mcpb sign`), `user_config` / `"sensitive": true`.

### 4b. MCP registry `server.json` - `code/m12/ship/registry/server.json` (copy `data/m12/ship/server.json`)
`name: com.example/fernhill-coffee` (example.com is a reserved domain), version 1.1.0, one `mcpb` package
(identifier = placeholder GitHub release URL, `fileSha256` = the real SHA-256 above, `transport: stdio`), `_meta` only under `io.modelcontextprotocol.registry/publisher-provided`.
Validated locally (`validate_server_json.py`, output `data/m12/ship/server_json_validate.txt`): published schema
`https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json` (latest dated version; registry release v1.8.7, 2026-10-30)
+ offline copies of the official-registry rules -> `server.json: VALID`. Each rule fires on a broken copy:
`fileSha256 000000000000... != sha256 of fernhill-coffee-1.1.0.mcpb dd688abd4107...`; `name: 'fernhill coffee' does not match '^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$'`;
`description ... is too long` (max 100); `'transport' is a required property`; `version 1.2.0 != manifest.json version 1.1.0`; `version 1.2.0 != serverInfo.version '1.1.0'`.
- The JSON Schema does NOT reject `"version": "^1.1.0"` (only the description says ranges are rejected); our local rule does.
- `mcp-publisher validate` is NOT offline: its source (`cmd/publisher/commands/validate.go`) POSTs the file to `<registry>/v0/validate`
  (default `registry.modelcontextprotocol.io`). Not run. Registry rules read from the repo docs: mcpb URL must contain "mcp" and be a
  GitHub/GitLab release; PyPI ownership = `mcp-name: <server name>` in the README; only `publisher-provided` `_meta` survives (4 KB max).

### 4c. Versioning - `code/m12/ship/schema_diff.py`, `make_snapshots.py`, `run_diffs.sh`; output `data/m12/versioning/schema_diff_runs.txt`
Snapshots from real `tools/list`: `tools_1.0.0.json` (v1), `tools_1.1.0.json`, `tools_2.0.0-rc1.json` (v2_bad); two one-rule edits of 1.1.0.
```
1.0.0 -> 1.1.0           3x EVAL (descriptions changed)            needs patch, declared minor  OK   "run the tool-choice eval before release"
1.1.0 -> 1.2.0-additive  MINOR tool added: get_stock; MINOR optional input 'note' added      needs minor  OK
1.1.0 -> "1.2.0"         MAJOR new required input 'pickup_time'; MAJOR 'items[].milk' enum lost ['none']
                         needs major, declared minor -> FAIL: version too small for this change   (exit 1)
1.1.0 -> 2.0.0-rc1       MAJOR tool removed x4 (get_menu, order_status, place_order, refund) + MINOR tool added x4   OK
```
Rules: MAJOR = tool removed/renamed, new required input, input removed (old callers' value is then silently ignored - see section 1),
type change, input enum value removed, output field removed. MINOR = tool / optional input / input enum value / output field added.
Description change = no contract change but a behaviour change: the eval (section 2) is the check. The schema diff cannot see v1.1's
case-insensitive fix at all. `tests/test_contract.py` (4 tests) pins `tools/list` to the 1.0.0 snapshot and tests the diff rules.

---

## Not covered in tutorials (all measured here)
- An eval that RUNS the chosen call on the real server finds bugs that a choice-only eval misses: v1 choice 92.6% but call 67.8%
  (case-sensitive names). Tool-name-only scoring would have shipped it.
- A "helpful" description can be worse than none: "Call this tool first" and "The person must confirm first" cut choice by up to 34 pts;
  "Tool." everywhere scored higher than v1's real descriptions.
- Claude follows the description over the name when they disagree; with a swapped pair it called `refund` for status requests.
- The expected "cryptic names" regression did not appear with 4 tools on Haiku 5.5; schema structure carries the meaning.
- Unit tests, snapshot test and schema diff all stay quiet (or only say "changed") for the two description PRs that fail the eval.
- MCP tracing in Python SDK 2.3.0 is on by default and crosses processes through `params._meta.traceparent`; client spans do not mark tool errors.
- Claude SDK spans contain org and workspace IDs by default.
- `mcpb pack` hash is SHA-1; the registry wants SHA-256. `.venv` is not excluded by default. uv bundle cold start 1.3-2.2 s vs 0.24 s warm.
- `mcp-publisher validate` sends the file to the registry; the JSON Schema alone accepts version ranges.

## UNCONFIRMED / not done
- No other model than Haiku 5.5; no Sonnet/Opus comparison of the same releases.
- Claude Desktop install of the `.mcpb` not done (UI); bundle signing not done; nothing published to any registry, PyPI or GitHub.
- The 15.5 ms gap inside `execute_tool fernhill__get_menu` (17.8 ms) vs its `MCP send` (2.3 ms): cause not investigated.
- Eval wall time per release not measured (8 concurrent requests).
- `data/m12/` holds no secret: `code/.env` was never printed; grep of all `data/m12/` for an API key prefix, the org/workspace ID and the home path = 0 hits (outside this sentence).

## Erratum (2026-11-05, checked against the raw eval files)
Finding 4's description of the v2-on-v1.1 failures is wrong. The cookie sizes guessed as 'regular'/'standard' are in
eval_v2_bad.json (v2 built from v1). The 6 failing rows of eval_v2_on_v1_1.json are: 2 with no tool call, 1 that picked
fernhill__mn_list, 3 calls to fernhill__po_create with empty or partial arguments (the m12 writer traced 4 of them to the
max_tokens 600 cut-off). The release was not re-run with a larger max_tokens. script/m12.md uses the corrected rows.
Finding 5: the 5 wrong refund calls used A-1041 three times and A-1042 twice (eval_v1_2_swap.json); the eval did not execute them.
