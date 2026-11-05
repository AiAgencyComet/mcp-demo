"""The context tax: how many tokens do the tool definitions of popular MCP servers cost, before the person types?
Connects to each server (stdio), saves its tools/list, counts tokens with the Claude token-counting API (free).
It downloads and runs these third-party servers locally (npx / docker), at pinned versions. No real tokens are given:
the Notion and GitHub servers get placeholder values, which is enough for tools/list.
Usage (run it yourself):  ../.venv-new/bin/python context_tax.py  -> data/m06/tax.json, data/m06/tools_<server>.json"""
import asyncio, json, logging, os, sys, time
from pathlib import Path
import anthropic
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters

logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "data" / "m06"; DATA.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / "code" / ".env"); api = anthropic.Anthropic()
FS = str(ROOT / "code" / "m06" / "fsroot"); os.makedirs(FS, exist_ok=True)
NPX = lambda pkg, *a: StdioServerParameters(command="npx", args=["-y", pkg, *a], env={**os.environ, "NO_COLOR": "1"})
SERVERS = {
    "fernhill": StdioServerParameters(command=str(ROOT / "code/.venv-new/bin/python"), args=[str(ROOT / "code/fernhill/server.py")]),
    "memory": NPX("@modelcontextprotocol/server-memory@2.1.0"),
    "filesystem": NPX("@modelcontextprotocol/server-filesystem@2.2.0", FS),
    "everything": NPX("@modelcontextprotocol/server-everything@2.2.1"),
    "playwright": NPX("@playwright/mcp@0.0.84"),
    "chrome-devtools": NPX("chrome-devtools-mcp@1.12.0"),
    "notion": StdioServerParameters(command="npx", args=["-y", "@notionhq/notion-mcp-server@2.6.1"],
                                    env={**os.environ, "NOTION_TOKEN": "ntn_placeholder_not_a_real_token"}),
    "github": StdioServerParameters(command="docker", args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                                    "ghcr.io/github/github-mcp-server:v1.4.0"],
                                    env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_placeholder_not_a_real_token"}),
}
Q = [{"role": "user", "content": "What does a large latte cost?"}]

def tok(model, tools=None):
    kw = {"tools": tools} if tools else {}
    return api.messages.count_tokens(model=model, messages=Q, **kw).input_tokens

async def list_tools(target):
    t0 = time.perf_counter()
    async with Client(target, read_timeout_seconds=120) as c:
        tools = (await c.list_tools()).tools
    return tools, time.perf_counter() - t0

async def main():
    out = {"question_tokens": {m: tok(m) for m in ("claude-haiku-5-5", "claude-sonnet-5-5")}, "servers": {}}
    for name, target in SERVERS.items():
        try:
            tools, secs = await list_tools(target)
        except BaseException as e:
            print(f"{name:16} FAILED {type(e).__name__}: {str(e)[:120]}"); continue
        defs = [{"name": f"{name}__{t.name}"[:64], "description": t.description or "", "input_schema": t.input_schema} for t in tools]
        (DATA / f"tools_{name}.json").write_text(json.dumps(defs, indent=1))
        row = {"tools": len(defs), "json_chars": len(json.dumps(defs)), "connect_s": round(secs, 1)}
        for m in ("claude-haiku-5-5", "claude-sonnet-5-5"):
            row[m] = tok(m, defs) - out["question_tokens"][m]
        out["servers"][name] = row
        print(f"{name:16} tools={row['tools']:3}  tokens(sonnet 5.5)={row['claude-sonnet-5-5']:6}  connect={row['connect_s']}s")
    (DATA / "tax.json").write_text(json.dumps(out, indent=1))

asyncio.run(main())
