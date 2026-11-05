"""A Claude agent that uses MCP servers. No framework: about 60 lines of logic.
The host (this file) owns one MCP client per server. Claude only sees tool definitions."""
import json, time
from pathlib import Path
import anthropic
from dotenv import load_dotenv
from mcp import Client

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
claude = anthropic.AsyncAnthropic()

def to_claude_tool(server: str, t) -> dict:
    """An MCP tool definition becomes a Claude tool definition. The name gets the server as a prefix."""
    return {"name": f"{server}__{t.name}", "description": t.description or "", "input_schema": t.input_schema}

def result_text(r) -> str:
    if r.structured_content is not None:
        return json.dumps(r.structured_content)
    return "\n".join(getattr(c, "text", "") for c in r.content)

async def run(question: str, servers: dict, model="claude-haiku-5-5", max_turns=8, system=None, log=None,
              extra_tools=None, tool_filter=None, max_tokens=1024):
    """servers = {"fernhill": <URL | StdioServerParameters | MCPServer>}. Returns a metrics dict."""
    clients, tools, owner = {}, [], {}
    try:
        for name, target in servers.items():
            c = Client(target); await c.__aenter__(); clients[name] = c
            for t in (await c.list_tools()).tools:
                if tool_filter and not tool_filter(name, t): continue
                ct = to_claude_tool(name, t); tools.append(ct); owner[ct["name"]] = (name, t.name)
        messages = [{"role": "user", "content": question}]
        m = {"model": model, "turns": 0, "input_tokens": 0, "output_tokens": 0, "model_ms": 0.0, "mcp_ms": 0.0,
             "tool_calls": [], "answer": None}
        kwargs = {"system": system} if system else {}
        for _ in range(max_turns):
            t0 = time.perf_counter()
            resp = await claude.messages.create(model=model, max_tokens=max_tokens, messages=messages,
                                                tools=tools + (extra_tools or []), **kwargs)
            m["model_ms"] += (time.perf_counter() - t0) * 1000; m["turns"] += 1
            m["input_tokens"] += resp.usage.input_tokens; m["output_tokens"] += resp.usage.output_tokens
            if log is not None: log.append(resp.model_dump(mode="json"))
            messages.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in resp.content]})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                m["answer"] = "".join(b.text for b in resp.content if b.type == "text"); break
            results = []
            for u in uses:
                server, tool = owner.get(u.name, (None, None))
                t1 = time.perf_counter()
                if server is None:
                    text, err = f"Unknown tool {u.name}", True
                else:
                    r = await clients[server].call_tool(tool, u.input)
                    text, err = result_text(r), bool(r.is_error)
                m["mcp_ms"] += (time.perf_counter() - t1) * 1000
                m["tool_calls"].append({"tool": u.name, "input": u.input, "is_error": err, "result": text[:300]})
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": text, "is_error": err})
            messages.append({"role": "user", "content": results})
        m["tools_offered"] = len(tools)
        return m
    finally:
        for c in clients.values():
            await c.__aexit__(None, None, None)
