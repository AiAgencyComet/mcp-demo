# Module 8 · UI inside the chat (MCP Apps) · results

Run: 2026-11-04, macOS, Python 3.12, `mcp` 2.3.0 (core spec 2026-07-28), Playwright 1.64.1 (Chromium 156 headless).
MCP Apps spec read: `ext-apps/specification/2026-01-26/apps.mdx` (Stable) and `specification/draft/apps.mdx`, plus
`ext-apps/src/spec.types.ts` and the reference host `examples/basic-host/src/{sandbox,implementation}.ts`.
Everything ran on 127.0.0.1 / localhost. No Claude API calls ($0). All shop data is invented (`code/m08/shop_m08.py`).

## What was built (code/m08/)

| File | What it is |
|---|---|
| `server.py` | Fernhill MCP App server. `Apps()` extension: tool `show_order_board` (model+app) and `mark_order_done` (app only), both bound to `ui://fernhill/order-board`; plain tool `order_status` (`_meta.ui.visibility: ["model"]`). stdio by default, `http 8810` for Streamable HTTP. |
| `board.html` | The View (12,152 characters). No SDK, no network: JSON-RPC 2.0 over `postMessage`. |
| `host/host_server.py` | Local test host backend: host origin `http://127.0.0.1:8820` (page + JSON-RPC forwarder + log writer), sandbox origin `http://localhost:8821` (`sandbox.html` with a CSP header built from `_meta.ui.csp`). |
| `host/host.html` | Host page: connects to the server, prefetches the UI template, scripted model turn, sandbox proxy, bridge, consent dialog, bridge log panel. |
| `host/sandbox.html` | Sandbox proxy (plain-JS port of the reference `sandbox.ts`). |
| `probe.py`, `raw_http.py`, `stdio_check.py` | In-process probe, raw HTTP wire transcript, stdio start check. |
| `capture.py`, `checks.py`, `run_capture.sh` | Playwright main capture; host-rule checks; runner that starts and stops both servers. |
| `claude_desktop_config.snippet.json` | The entry for the hand recording in Claude Desktop. |

Re-run: `cd code/m08 && ./run_capture.sh` (main capture) and `./run_capture.sh checks.py`. Each run starts a fresh server (the
shop lives in memory) and kills both servers on exit (checked with `pgrep`: none left).

## Outputs (data/m08/)

- `tools_list.json`, `resources_list.json`, `resource_read_order_board.json` (raw `ui://` read), `order_board.html` (the HTML from that read), `server_capabilities.json`
- `call_show_order_board_apps_client.json`, `call_show_order_board_plain_client.json`, `call_mark_order_done_direct.json`, `call_mark_order_done_bad_id.json`
- `bridge_log.jsonl` (31 messages, main run), `bridge_log_summary.txt` (one line per message), `checks_bridge_log.jsonl` (28, checks run)
- Transcripts: `probe_transcript.txt`, `raw_http_transcript.txt`, `stdio_check.txt`, `capture_transcript.txt`, `checks_transcript.txt`, `console.txt`
- Screens, 2560x1440 (1280x720 CSS at DPR 2), in `screens/`:
  `01_host_connected` · `02_board_loading` · `03_board_loaded` (+ `03b_board_card` crop) · `04_consent` · `05_marked_done` (+ `05b_board_card_done` crop) · `06_model_context` · `07_after_teardown` · `check_deny`
- Video: `host_run.mp4`, 2560x1440, 30 fps, 10.9 s, real speed (see "Capture notes").

## Verified facts (ran → came back)

**F1. Exact Python API.** `from mcp.server.apps import Apps, client_supports_apps`; `apps = Apps()`;
`@apps.tool(resource_uri="ui://...", visibility=["model","app"], title=..., annotations=...)`;
`apps.add_html_resource(uri, html, name=, title=, description=, csp=ResourceCsp(...), permissions=ResourcePermissions(...), domain=, prefers_border=)`;
`MCPServer("fernhill-board", extensions=[apps])`. Constants: `EXTENSION_ID = "io.modelcontextprotocol/ui"`, `APP_MIME_TYPE = "text/html;profile=mcp-app"`.
SDK guards (read in `mcp/server/apps.py`): a non-`ui://` URI raises `ValueError`; a tool bound to an unregistered resource raises at
`MCPServer(...)`; `meta={"ui": ...}` on `apps.tool` is refused (the decorator owns `_meta.ui`); a `ui://` resource with another MIME type is refused.

**F2. The tool carries the link; the server advertises the extension.** `raw_http.py` (POST to `http://127.0.0.1:8810/mcp`):
```
Mcp-Method: server/discover   -> result.capabilities.extensions = {"io.modelcontextprotocol/ui": {}}
Mcp-Method: tools/list
  tool show_order_board: _meta = {"ui": {"resourceUri": "ui://fernhill/order-board", "visibility": ["model", "app"]}}
  tool mark_order_done: _meta = {"ui": {"resourceUri": "ui://fernhill/order-board", "visibility": ["app"]}}
  tool order_status: _meta = {"ui": {"visibility": ["model"]}}
  ttlMs=0 cacheScope=private
```

**F3. The template is a resource with the MCP App MIME type.** `resources/read` with header `Mcp-Name: ui://fernhill/order-board`:
```
contents[0].mimeType = text/html;profile=mcp-app
contents[0].text = 12152 characters, starts '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
contents[0]._meta = {"ui": {"prefersBorder": true}}
```
The SDK puts `_meta.ui` on both the `resources/list` entry and the `resources/read` content item (spec draft: the content item wins).

**F4. Graceful degradation is one branch on the client's capability.** `client_supports_apps(ctx)` is true only if the client sent
`capabilities.extensions["io.modelcontextprotocol/ui"].mimeTypes` containing `text/html;profile=mcp-app`. `probe.py`:
```
[client WITH io.modelcontextprotocol/ui] The order board is on screen. 5 open orders: ...
[client WITHOUT the extension]           Order board (text only). 5 open orders: ...
```
Both return the same 5-line text list in `content` (what the model reads) and the full 7 orders in `structuredContent` (what the View draws).

**F5. Visibility is a HOST rule, not server access control.** The SDK server does not check visibility. `probe.py`, no host in between:
`mark_order_done A-1043 (direct, no host) -> A-1043 (Mara) is done. 4 orders are open.` (an "app only" tool, called by a plain client).
Our host enforces it (`checks_transcript.txt`), as the spec requires ("Host MUST reject `tools/call` requests from apps for tools that don't include `app`"):
```
View got: {"error": {"code": -32000, "message": "Tool order_status is not available to apps (visibility [\"model\"])"}}
```
And the model never sees `mark_order_done`: the host's model tool list is `show_order_board`, `order_status` (`01_host_connected.png`).

**F6. Full lifecycle on the wire, in order** (`bridge_log_summary.txt`, main run; t = ms since the host page loaded):
```
  1    7.4  host -> server   server/discover            (connect: 4 round trips, all done at 22.2 ms)
  7   19.7  host -> server   resources/read  Mcp-Name: ui://fernhill/order-board   <- prefetch, BEFORE any tool call
 10 2126.2  host -> server   tools/call  Mcp-Name: show_order_board               <- the (scripted) model call
 11 2133.8  server -> host   tools/call result
 12 2137.7  sandbox -> host  ui/notifications/sandbox-proxy-ready
 13 2138.0  host -> sandbox  ui/notifications/sandbox-resource-ready  (html 12,152 chars, csp: none)
 14 2139.7  view -> host     ui/initialize   {"appInfo":{"name":"fernhill-order-board",...},"appCapabilities":{"availableDisplayModes":["inline"]},"protocolVersion":"2026-01-26"}
 15 2139.9  host -> view     ui/initialize result (hostInfo, hostCapabilities, hostContext.toolInfo, containerDimensions {width 786, maxHeight 640})
 16 2140.5  view -> host     ui/notifications/initialized
 17 2140.5  host -> view     ui/notifications/tool-input {"arguments": {}}
 19 3942.1  host -> view     ui/notifications/tool-result   (held 1.8 s on purpose, see Capture notes)
 21 5966.4  view -> host     tools/call {"name":"mark_order_done","arguments":{"order_id":"A-1043"}}
 22 5966.7  host -> person   consent: ask (readOnlyHint: false)
 23 7167.4  person -> host   consent: allow
 24 7167.8  host -> server   tools/call  Mcp-Name: mark_order_done
 25 7184.4  server -> host   result "A-1043 (Mara) is done. 4 orders are open."
 26 7184.7  host -> view     tools/call result (same CallToolResult)
 27 7185.2  view -> host     ui/update-model-context "The person marked order A-1043 (Mara) done on the order board. Open orders now: 4."
 30 9777.9  host -> view     ui/resource-teardown {"reason":"conversation closed"}  -> 31 view -> host {}
```
31 messages: 12 host↔server (HTTP), 14 View↔host (postMessage), 2 sandbox↔host, 3 consent decisions.
HTTP round trip from the forwarder to the server: 0.97 to 2.53 ms. Sandbox ready → View initialized: 2.8 ms.

**F7. The button click is a normal `tools/call` that goes through the host, and through the same consent gate as a model call.**
In our host one function decides for both callers, from the tool's annotations, not from who asks:
`show_order_board` asked by the model → `auto-allow (readOnlyHint: true)`; `mark_order_done` asked by the View → dialog "Allow this tool call?"
(`04_consent.png`). Deny path (`checks_transcript.txt`): `View toast: 'Not done: The person denied mark_order_done'` and the server state did not change:
`server after Deny, order_status A-1044 -> 'A-1044: ready'`. The policy is ours; the spec says the host "MAY decide to block some messages
or subject them to further user approval".

**F8. The tool result can arrive before the View exists.** Result at 2133.8 ms (seq 11), View's first message at 2139.7 ms (seq 14).
The host must keep the result and send it only after `ui/notifications/initialized` and `ui/notifications/tool-input` (spec: tool-input
"is required before sending `ui/notifications/tool-result`"; "Host MUST NOT send any request or notification to the View before it receives an `initialized` notification").

**F9. Sandbox: no `ui.csp` → restrictive default, and the View cannot reach the network or the host page.** `checks_transcript.txt`:
```
sandbox.html Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'self'
View fetch to the MCP server directly: {"error": "TypeError: Failed to fetch", "seen": ["connect-src http://127.0.0.1:8810/mcp"]}
view: window.top.document.title -> SecurityError: ... Blocked a frame with origin "http://localhost:8821" from accessing a cross-origin frame
```
So the only path from the View to the server is the host bridge. The View document is `about:blank` written by the proxy (origin `http://localhost:8821`),
and it inherits the proxy page's CSP header.

**F10. stdio works (the Claude Desktop path).** `stdio_check.txt`: protocol 2026-07-28, same 3 tools with the same `_meta.ui`, `resources/read -> text/html;profile=mcp-app 12152 characters`.

## Surprises / not in tutorials

1. Two version numbers: the core protocol is 2026-07-28, but the View↔host protocol is MCP Apps `2026-01-26` (`protocolVersion` in `ui/initialize`). The host is an MCP *server* to the View and an MCP *client* to the real server.
2. F5: visibility `["app"]` hides a tool from the model only if the host obeys it. The server must still check permission on every tool.
3. F8: the order race (result before View). A host that sends the result at once loses it.
4. Chrome prints a warning for the spec-required flags: `An iframe which has both allow-scripts and allow-same-origin for its sandbox attribute can escape its sandboxing.` The isolation comes from the separate origin (`localhost:8821` vs `127.0.0.1:8820`), which F9 shows works. Same-origin hosting of the View would break it.
5. Stable vs draft spec: the 2026-01-26 text says a web host "MUST wrap the View ... through an intermediate Sandbox proxy" (`sandbox-proxy-ready` / `sandbox-resource-ready`); the draft drops that mandate (single or double iframe allowed), and requires the iframe document to be served by "a server the Host controls". The draft and `spec.types.ts` also add messages not in the stable text: `ui/download-file`, `ui/notifications/request-teardown`, host capabilities `updateModelContext`, `message`, `sampling`, and app-provided tools.
6. `structuredContent` is for the View; the spec's best practice says it is "not added to model context". So `content` must carry what the model needs (F4).
7. Claude Code docs (`research/cc-mcp.md` l.1503): `ui://` resources "don't appear in the `@` suggestions or in the resource list tool's results"; "Reading a UI resource by its URI still works."
8. The SDK's `ToolError` text reaches the host with a prefix: `isError: True | Error executing tool mark_order_done: No order A-9999. Order IDs look like A-1043.`
9. `resources/read` results also carry `ttlMs: 0, cacheScope: "private"` (the cache hints of module 9), useful for template prefetch caching.

## Honest limits of this demo (say these in the script)

- The model turn is **scripted**: the host calls `show_order_board` itself (labelled "scripted turn" on screen). No LLM was called.
- The host holds the `tool-result` for 1.8 s (`?hold=1800`) so the loading state is visible on video. The real result came 7.6 ms after the request (seq 10 → 11).
- The consent dialog, the "auto-allow when readOnlyHint is true" rule and all host UI are our test host, not Claude. Claude's own behavior must come from the hand recording below.
- The host shown is ours ("Local test host"), not an imitation of any product UI.

## Bridge log format (for the animation)

One JSON object per line, file order = time order. Fields: `seq`; `t_ms` (ms since the host page loaded); `wall` (ISO time);
`hop` = `host-server` (HTTP) | `view-host` (postMessage) | `sandbox-host` | `host-gate` (consent); `from`/`to` = `host` | `server` | `view` | `sandbox` | `person`;
`kind` = `request` | `response` | `notification` | `consent`; `method` (for responses: the method of the request); `id`;
`msg` = the exact JSON-RPC message (host-server requests include the `_meta` envelope; `sandbox-resource-ready` includes the full HTML);
host-server requests add `http_headers` (`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`), responses add `http_status` and `server_ms`;
consent entries add `decision` (`auto-allow` | `ask` | `allow` | `deny` | `reject`) and `note`.

## Capture notes

- Screenshots: Playwright `page.screenshot` at viewport 1280x720, `device_scale_factor=2` → 2560x1440.
- Video: Playwright's `record_video` and the CDP screencast both produce CSS-pixel frames (the first gave a 2560x1440 file with the page in the top-left quarter). CDP `Page.captureScreenshot` with `clip.scale: 2` is sharp but resizes the page while it shoots (the View sent 21 `size-changed` messages, widths 786 and 2066). Final method: a loop of `page.screenshot` (about 20 per second during the run), placed on a 30 fps timeline by capture time. No side effects: the log has the normal 31 entries.
- For the edit, the still screenshots are sharper than the video; use the video for motion (click, dialog, row change) and stills for holds.

## Hand recording in Claude Desktop (needs the user)

Privacy: record in a fresh chat; hide the chat history sidebar, the account name and email (mask in the edit if visible). All data is invented.

1. Open Claude Desktop → Settings → Developer → Edit Config. This opens `~/Library/Application Support/Claude/claude_desktop_config.json`.
2. Add the `fernhill-board` entry from `code/m08/claude_desktop_config.snippet.json` inside `"mcpServers"` (keep any other entries). Save.
3. Quit Claude Desktop fully (Cmd+Q) and open it again. The server starts with Claude Desktop; each restart resets the board (A-1043 is "Ready" again).
4. In a new chat, open the "+" → Connectors menu (or the tools menu) and check that `fernhill-board` is on with 2 tools for the model. Record this: note if `mark_order_done` is absent (visibility `["app"]`).
5. Type: `Show me the open orders on the Fernhill order board.` Record Claude's tool-permission prompt if one appears, then the board as it renders inline.
6. Click "Mark done" on A-1043 (Mara). Record whether Claude Desktop asks for approval for this UI-initiated call, and the row change and toast.
7. Type: `Which orders are still open?` Record whether the answer knows A-1043 is done (that is the `ui/update-model-context` path; Claude may also call `order_status`).
8. Optional contrast in Claude Code: `claude mcp add fernhill-board -- /path/to/mcp-demo/code/.venv-new/bin/python /path/to/mcp-demo/code/m08/server.py`, then ask the same question. Expected (docs): text only, no board. Remove it after with `claude mcp remove fernhill-board`.
9. Remove the entry from `claude_desktop_config.json` after recording.

## UNCONFIRMED (not tested by us)

- That Claude Desktop renders MCP Apps from a **local stdio** server. Support is documented for interactive connectors (support.claude.com article 13454812, "available for all users on Claude, Cowork, Claude Desktop, and Claude for iOS/Android") and the ext-apps README tells developers to add stdio servers to "Claude Desktop, VS Code, etc." Step 5 confirms or refutes it.
- How Claude Desktop treats a UI-initiated `tools/call` (approval prompt or not), whether it hides `visibility: ["app"]` tools from the model, and whether `ui/update-model-context` reaches the model on the next turn (steps 4, 6, 7).
- Which framing Claude uses (double iframe on `claudemcpcontent.com`-style domains is suggested by the spec's `domain` example, not verified).
- Claude Code showing text only: from Anthropic's docs and the task brief, not run here (it would use the user's Claude Code account).
