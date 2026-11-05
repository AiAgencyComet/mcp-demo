# Scene m02-01s "What you need" · sources (written 2026-11-05, review fix: newcomer setup scene)

## 1 Python
- Our runs: `code/.venv-new/bin/python --version` -> `Python 3.12.11` (run 2026-11-05). `code/.venv-new/pyvenv.cfg`: version_info = 3.12.11
  (the course made the venv with uv 0.11.6; the scene shows the standard venv commands).
- Commands, as in the Claude API quickstart (platform.claude.com/docs/en/get-started, read 2026-11-05):
  `python3 -m venv .venv && source .venv/bin/activate` and `pip install anthropic`.
  Windows activate script: `.venv\Scripts\activate` (Python venv docs).

## 2 Packages (versions installed in code/.venv-new/lib/python3.12/site-packages, also repo/requirements.txt)
- mcp 2.3.0 (mcp-2.3.0.dist-info) · anthropic 2.5.0 (anthropic-2.5.0.dist-info) · python-dotenv 1.2.4 (python_dotenv-1.2.4.dist-info)
- Scene line: `pip install mcp==2.3.0 anthropic==2.5.0 python-dotenv==1.2.4`

## 3 API key in .env
- Console: "Create a Claude Console account. Sign up for a Claude Console account, or sign in to the one you have."
  (platform.claude.com/docs/en/get-started, read 2026-11-05)
- Our code reads the key from code/.env: `code/agent/agent.py` line 9 `load_dotenv(Path(__file__).resolve().parents[1] / ".env")`;
  `anthropic.Anthropic()` reads ANTHROPIC_API_KEY from the environment. code/.env is mode 600 and never shown.
- Cost: "the API is paid per token". Module 1 token count: one MCP tool call = 1,656 input tokens (data/m01/three_ways.json, medians of 10).

## 4 Claude Code (code.claude.com/docs/en/setup, read 2026-11-05, verbatim)
- "macOS, Linux, WSL: curl -fsSL https://claude.ai/install.sh | bash"
- "Windows PowerShell: irm https://claude.ai/install.ps1 | iex"
- "When the installer finishes, open a new terminal window and run claude --version. A working installation prints a version number."
- "Claude Code requires a Pro, Max, Ultra, Team, Enterprise, or Console account. The free claude.ai plan does not include Claude Code access."

## 5 Code
- "The code for every module is on GitHub. The link is in the description." (team-lead instruction; the repo is being prepared in repo/;
  the URL is not shown on screen).

## m02-07 cache sentence
- "Cache read tokens are 0.1 times the base input tokens price (see the table footnote for per-model exceptions)." Exceptions listed:
  Fable 5.1 / Mythos 5.1 0.025x, Opus 5.5 / Sonnet 5.5 0.05x; "All other models use the standard 0.1x multiplier" -> Haiku 5.5 = 0.1x.
  (platform.claude.com/docs/en/build-with-claude/prompt-caching, read 2026-11-05)
