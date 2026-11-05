# MCP Full Course 2026 — code and measured results

All the code and the run data from the DeepOnAI course **"MCP Full Course 2026: Build MCP Servers in Python (New Spec)"**
(YouTube, about 3 h 54 min). Every number in the video comes from a run of the code in this repository.

- MCP specification **2026-07-28** (stateless requests, `server/discover`, multi round-trip, extensions: MCP Apps and Tasks)
- Python SDK **mcp 2.3.0** (`requirements.txt`); the old-spec comparisons use **mcp 1.30.0** (`requirements-old-spec.txt`)
- Models: Claude Haiku 5.5 and Claude Sonnet 5.5 (November 2026)

Fernhill Coffee, its staff, customers and orders are invented. Everything runs on your own machine (localhost).

## Setup

```bash
python3.12 -m venv code/.venv-new && code/.venv-new/bin/pip install -r requirements.txt
python3.12 -m venv code/.venv-old && code/.venv-old/bin/pip install -r requirements-old-spec.txt   # only for the old-spec comparisons
cp code/.env.example code/.env   # put your Anthropic API key in code/.env; never commit it
```

The scripts use the two environments at `code/.venv-new` and `code/.venv-old`. Experiments that call Claude use your API
key and cost money per token; the results files list the token counts of our runs.

## Map: video module → code → results

| Module | Topic | Code | Results |
|---|---|---|---|
| 1 | MCP vs API vs a tool call | `code/m01`, `code/agent` | `data/m01` |
| 2 | First server (11 lines), Claude Code, scopes | `code/m02` | `data/m02/RESULTS.md` |
| 3 | The protocol raw: curl, no SDK, old vs new wire | `code/m03` | `data/m03` |
| 4 | Fernhill server: tools, resources, prompts, ToolError | `code/fernhill` | `data/m04` |
| 5 | Tool choice vs tool count, what Claude reads, tool search | `code/m05`, `code/m05b` | `data/m05/RESULTS.md`, `data/m05b` |
| 6 | Your own agent, the context tax of real servers | `code/agent`, `code/m06`, `code/m06b` | `data/m06`, `data/m06b/RESULTS.md` |
| 7 | Multi round-trip (sealed request state), Tasks, Claude Code timeouts | `code/m07`, `code/m07b`, `code/m07c` | `data/m07*` |
| 8 | MCP Apps: the order board and a test host | `code/m08` | `data/m08/RESULTS.md` |
| 9 | Kill test, ask-back across copies, serverless model, cache hints, header gateway | `code/m09`, `code/m09s`, `code/m09b` | `data/m09/RESULTS.md`, `data/m09s/RESULTS.md`, `data/m09b/RESULTS.md` |
| 10 | OAuth 2.1: scopes, step-up, PKCE, iss | `code/m10` | `data/m10/RESULTS.md` |
| 11 | Security concepts (no attack code, by design) | — | — |
| 12 | Unit tests, evals with a gate, tracing, packaging (.mcpb), registry | `code/m12` | `data/m12/RESULTS.md` |

Each `RESULTS.md` says how the run was made, the sample size, and what was not tested.

## Notes
- The Tasks extension in `code/m07b/tasks_ext.py` is the course's own code (the Python SDK 2.3.0 has no Tasks support).
- `code/m10` contains a local test authorization server; the tokens in `data/m10` were issued by it on localhost and expired.
- One synthetic test request in `data/m05` used a realistic email address; it was replaced with `@example.com`.
- Local paths in configs and logs were replaced with `/path/to/mcp-demo` or `~`.

## License
MIT (see LICENSE).
