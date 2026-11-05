"""The unchanged Fernhill server (code/fernhill/server.py), run over Streamable HTTP with tracing on.
  python traced_server.py <port> <out_dir>
Adds two things from the outside, no change to server.py:
  1. a tracer provider -> the SDK's built-in OpenTelemetryMiddleware now emits one SERVER span per request
  2. one business span per tool (fernhill.<tool>) and a log of the raw params._meta that arrived"""
import functools, json, logging, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "fernhill")]
from otel_setup import setup

port, out = int(sys.argv[1]), Path(sys.argv[2])
setup("fernhill-mcp-server", out / "server_spans.jsonl")          # before the server import, before any span

from opentelemetry import trace
from opentelemetry.trace import StatusCode
import server                                                      # code/fernhill/server.py

tracer = trace.get_tracer("fernhill")
meta_log = out / "server_meta_seen.jsonl"; meta_log.write_text("")


class RecordMeta:
    """Context-tier middleware: write the raw `_meta` of each request exactly as it came off the wire."""
    async def __call__(self, ctx, call_next):
        raw = dict((ctx.params or {}).get("_meta") or {})
        with meta_log.open("a") as f:
            f.write(json.dumps({"method": ctx.method, "name": (ctx.params or {}).get("name"), "_meta": raw}) + "\n")
        return await call_next(ctx)

server.mcp._lowlevel_server.middleware.append(RecordMeta())        # after the SDK's OpenTelemetryMiddleware


def traced(name, fn):
    @functools.wraps(fn)
    def run(**kw):
        with tracer.start_as_current_span(f"fernhill.{name}") as span:
            if "items" in kw: span.set_attribute("fernhill.items.count", len(kw["items"]))
            if "order_id" in kw: span.set_attribute("fernhill.order.id", kw["order_id"])
            try:
                result = fn(**kw)
            except Exception as e:
                span.set_status(StatusCode.ERROR, str(e)); span.set_attribute("error.type", type(e).__name__)
                raise
            if hasattr(result, "order_id"):
                span.set_attributes({"fernhill.order.id": result.order_id, "fernhill.order.total": result.total})
            return result
    return run

for t in server.mcp._tool_manager.list_tools():
    t.fn = traced(t.name, t.fn)

logging.disable(logging.WARNING)
server.mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
