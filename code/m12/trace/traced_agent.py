"""One agent request, traced end to end across two processes.
  host process (this file):  invoke_agent -> anthropic.messages.create (Claude SDK span)
                                          -> execute_tool -> MCP send tools/call (MCP SDK client span, injects traceparent)
  server process:            tools/call place_order (MCP SDK server span, parent read from params._meta) -> fernhill.place_order
The two processes share nothing but the HTTP request. Spans go to data/m12/trace/*.jsonl; tree.py joins them."""
import asyncio, json, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "data" / "m12" / "trace"
sys.path[:0] = [str(HERE)]
from otel_setup import setup

provider = setup("fernhill-host", OUT / "host_spans.jsonl")       # before the Claude client exists

import anthropic
from dotenv import load_dotenv
from mcp import Client
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

load_dotenv(ROOT / "code" / ".env")
PORT, MODEL = 8212, "claude-haiku-5-5"
URL = f"http://127.0.0.1:{PORT}/mcp"
QUESTION = "I want a large oat latte for pickup, name Sam. What is the total, and what is my order ID?"
tracer = trace.get_tracer("fernhill-host")


def result_text(r):
    if r.structured_content is not None:
        return json.dumps(r.structured_content)
    return "\n".join(getattr(c, "text", "") for c in r.content)


async def agent(question, log):
    claude = anthropic.AsyncAnthropic()
    with tracer.start_as_current_span("invoke_agent fernhill-helper", kind=SpanKind.INTERNAL,
                                      attributes={"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "fernhill-helper"}) as root:
        async with Client(URL) as mcp:
            tools = [{"name": f"fernhill__{t.name}", "description": t.description or "", "input_schema": t.input_schema}
                     for t in (await mcp.list_tools()).tools]
            messages = [{"role": "user", "content": question}]
            for turn in range(6):
                resp = await claude.messages.create(model=MODEL, max_tokens=2000, tools=tools, messages=messages)
                log.append({"turn": turn + 1, "stop_reason": resp.stop_reason, "usage": resp.usage.model_dump(),
                            "content": [b.model_dump(mode="json") for b in resp.content]})
                messages.append({"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in resp.content]})
                if resp.stop_reason != "tool_use":          # also covers max_tokens: never run a cut-off tool call
                    answer = "".join(b.text for b in resp.content if b.type == "text")
                    root.set_attribute("fernhill.turns", turn + 1)
                    return answer
                results = []
                for u in (b for b in resp.content if b.type == "tool_use"):
                    with tracer.start_as_current_span(f"execute_tool {u.name}", kind=SpanKind.INTERNAL, attributes={
                            "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": u.name, "gen_ai.tool.call.id": u.id}) as span:
                        r = await mcp.call_tool(u.name.removeprefix("fernhill__"), u.input)
                        text = result_text(r)
                        if r.is_error:
                            span.set_status(StatusCode.ERROR, text[:200])
                    log.append({"tool": u.name, "input": u.input, "is_error": bool(r.is_error), "result": text})
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": text, "is_error": bool(r.is_error)})
                messages.append({"role": "user", "content": results})


async def bad_order_smoke():
    """No model: one direct call with a drink that is not on the menu, to show an error span on both sides."""
    with tracer.start_as_current_span("smoke bad_order"):
        async with Client(URL) as mcp:
            r = await mcp.call_tool("place_order", {"items": [{"drink": "mocha", "size": "large"}],
                                                    "handoff": {"kind": "pickup", "name": "Sam"}})
            return r.is_error, r.content[0].text


def wait_port(port, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError("server did not start")


def main():
    srv = subprocess.Popen([sys.executable, str(HERE / "traced_server.py"), str(PORT), str(OUT)],
                           stdout=subprocess.DEVNULL, stderr=open(OUT / "server_stderr.txt", "w"))
    try:
        wait_port(PORT)
        log = []
        t0 = time.perf_counter()
        answer = asyncio.run(agent(QUESTION, log))
        ms = (time.perf_counter() - t0) * 1000
        smoke = asyncio.run(bad_order_smoke())
        provider.force_flush()
        (OUT / "agent_run.json").write_text(json.dumps({"question": QUESTION, "model": MODEL, "answer": answer,
                                                        "wall_ms": round(ms), "log": log, "smoke_bad_order": smoke}, indent=1))
        print("ANSWER:", answer)
        print("tool calls:", [(e["tool"], e["is_error"]) for e in log if "tool" in e], "| wall", round(ms), "ms")
        print("smoke bad order:", smoke)
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill(); srv.wait()
        print("server exit code:", srv.returncode)


if __name__ == "__main__":
    main()
