# Module 2 · first server + hosts (measured 2026-11-05)

- `code/m02/first_server.py`: 11 lines (MCPServer, one tool, `mcp.run()` = stdio). Type hint = schema, docstring = description.
- Claude Code, headless (data/m02/term/claude_p.txt, claude_p.json):
  `claude -p "What does a large latte cost at Fernhill?" --mcp-config fernhill.mcp.json --strict-mcp-config --allowedTools mcp__fernhill__get_price --model haiku`
  → answered from the tool ($4.50; noted the tool has no sizes). JSON: 4 turns, 7,689 ms, $0.0016;
  usage: 8 input + 127,299 cache-read + 595 cache-creation tokens, 413 output. Claude Code's own prompt + tools dwarf one MCP tool; caching makes it cheap.
  Tool names in Claude Code: `mcp__<server>__<tool>`.
- Scopes (data/m02/term/scopes.txt, personal server list redacted): `--scope project` writes `.mcp.json` (shared, in the repo);
  `--scope local` writes `~/.claude.json` keyed by project path (private). Same name in both → `claude mcp get fernhill` shows
  "Scope: Local config (private to you in this project)" = local wins. Help text: unapproved `.mcp.json` servers show "⏸ Pending approval".
- `claude mcp serve` (data/m02/claude_code_tools.json): Claude Code as an MCP server exposes 25 tools (Agent, Bash, Read, Edit, Write, ...)
  = 36,450 tokens of definitions (Haiku count) — more than GitHub's whole server (14,687).
- Claude Code also has `claude mcp add-from-claude-desktop` (Mac and WSL) and `add-json`.

## Needs the user to record (screen capture with personal data hidden)
1. Claude Desktop: Settings → Developer → Edit Config, add
   {"mcpServers": {"fernhill": {"command": "/path/to/mcp-demo/code/.venv-new/bin/python", "args": ["/path/to/mcp-demo/code/m02/first_server.py"]}}}
   restart Claude Desktop, ask "What does a latte cost at Fernhill?", approve the tool, record the answer. Hide chat list, name, email.
2. VS Code: `.vscode/mcp.json` with {"servers": {"fernhill": {"type": "stdio", "command": "/path/to/mcp-demo/code/.venv-new/bin/python", "args": ["/path/to/mcp-demo/code/m02/first_server.py"]}}},
   start it from the file's CodeLens, ask Copilot Chat in Agent mode the same question. (Check current VS Code docs before recording.)
3. (Optional) the .mcpb one-click install from module 12.
