"""Connect to `claude mcp serve` (Claude Code as an MCP server) and list its tools. We call no tool."""
import asyncio, json, logging
from pathlib import Path
import anthropic
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; load_dotenv(ROOT / "code" / ".env")
async def main():
    async with Client(StdioServerParameters(command="claude", args=["mcp", "serve"]), read_timeout_seconds=60) as c:
        tools = (await c.list_tools()).tools
    defs = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in tools]
    (ROOT / "data/m02/claude_code_tools.json").write_text(json.dumps(defs, indent=1))
    api = anthropic.Anthropic(); q = [{"role": "user", "content": "hi"}]
    base = api.messages.count_tokens(model="claude-haiku-5-5", messages=q).input_tokens
    tok = api.messages.count_tokens(model="claude-haiku-5-5", messages=q, tools=defs).input_tokens - base
    print(len(defs), "tools:", ", ".join(t["name"] for t in defs)); print("tool definitions:", tok, "tokens")
asyncio.run(main())
