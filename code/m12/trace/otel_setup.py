"""One OpenTelemetry setup for both processes: a tracer provider that writes every finished span as one JSON line."""
import json
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class JsonLinesExporter(SpanExporter):
    def __init__(self, path: Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text("")

    def export(self, spans):
        with self.path.open("a") as f:
            for s in spans:
                f.write(json.dumps(json.loads(s.to_json())) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def setup(service_name: str, out: Path) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(JsonLinesExporter(out)))   # written at span end: survives a kill
    trace.set_tracer_provider(provider)
    return provider
