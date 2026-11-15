"""OpenTelemetry tracing for guard-api (Architecture.md section 13).

The service owns its own TracerProvider (not the global one), so tests can attach an in-memory exporter.
Spans: scan (one per text), normalize, ollama.call (one per window attempt), policy. No span carries raw text.

Exporter (env OTEL_EXPORTER): "file" (default) appends one JSON object per span to OTEL_FILE
(default traces.jsonl next to the audit DB), "console" prints spans, "none" keeps spans in memory only.
"""

import json
import threading
from collections.abc import Sequence
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter,
                                            SpanExportResult)

_provider = TracerProvider(resource=Resource.create({"service.name": "guard-api"}))
_configured: set[str] = set()


class JsonLinesSpanExporter(SpanExporter):
    """Appends finished spans to a file, one compact JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        """Create the parent folder; the file is opened per export."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Write the spans."""
        lines = []
        for s in spans:
            ctx = s.get_span_context()
            lines.append(json.dumps({
                "name": s.name, "trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}",
                "parent_id": f"{s.parent.span_id:016x}" if s.parent else None,
                "start_ns": s.start_time, "end_ns": s.end_time,
                "duration_ms": round((s.end_time - s.start_time) / 1e6, 3) if s.end_time and s.start_time else None,
                "attributes": dict(s.attributes or {}),
            }))
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Nothing to release."""


def get_tracer() -> trace.Tracer:
    """Tracer for guard spans."""
    return _provider.get_tracer("guard")


def add_exporter(exporter: SpanExporter) -> None:
    """Send finished spans to an exporter (console or file in the service, in-memory in tests)."""
    _provider.add_span_processor(SimpleSpanProcessor(exporter))


def configure(kind: str, file_path: str | Path) -> None:
    """Attach the configured exporter once per process: file, console, or none."""
    key = f"{kind}:{file_path}" if kind == "file" else kind
    if kind == "none" or key in _configured:
        return
    if kind == "console":
        add_exporter(ConsoleSpanExporter())
    elif kind == "file":
        add_exporter(JsonLinesSpanExporter(file_path))
    else:
        raise ValueError(f"OTEL_EXPORTER must be file, console, or none, got {kind!r}")
    _configured.add(key)


def enable_console() -> None:
    """Print spans to stdout (kept for OTEL_CONSOLE=true)."""
    configure("console", "")
