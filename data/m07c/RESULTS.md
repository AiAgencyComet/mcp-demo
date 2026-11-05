# Module 7c · Claude Code and slow remote tools (measured 2026-11-05, Claude Code 2.1.318, `claude -p --model haiku`)
Tool: export_sales_report(seconds) on a local Streamable HTTP server (code/m07c/). Config type "http".
| server response mode | tool time | per-server "timeout" | result | wall time |
|---|---|---|---|---|
| SSE stream (SDK default) | 20 s | none | ok | 28 s |
| SSE stream (SDK default) | 90 s | none | ok | 99 s |
| SSE stream | 90 s | 150000 ms | ok | 99 s |
| plain JSON (`json_response=True`) | 90 s | none | FAILED: "The Fernhill export_sales_report call with seconds=90 timed out" | 65 s |
| plain JSON | 90 s | 150000 ms | ok | 96 s |
Docs (code.claude.com env-vars, via research/anthropic_mcp_features.md): "For an HTTP, SSE, or claude.ai connector server, each request
also times out after 60 seconds by default." Measured: the 60 s limit hits a plain-JSON response; an SSE-streamed response of 90 s
completed with the default config. Fix for slow tools: per-server `timeout` (ms), or stream, or (best) a Task (module 7b).
