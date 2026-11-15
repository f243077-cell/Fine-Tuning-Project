"""OpenTelemetry tracing for guard-api (Architecture.md section 13).

The service owns its own TracerProvider (not the global one), so tests can attach an in-memory exporter.
Spans: scan (one per text), normalize, ollama.call (one per window attempt), policy.
"""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter

_provider = TracerProvider(resource=Resource.create({"service.name": "guard-api"}))
_console_added = False


def get_tracer() -> trace.Tracer:
    """Tracer for guard spans."""
    return _provider.get_tracer("guard")


def add_exporter(exporter: SpanExporter) -> None:
    """Send finished spans to an exporter (console in the service, in-memory in tests)."""
    _provider.add_span_processor(SimpleSpanProcessor(exporter))


def enable_console() -> None:
    """Print spans to stdout once (OTEL_CONSOLE=true)."""
    global _console_added
    if not _console_added:
        add_exporter(ConsoleSpanExporter())
        _console_added = True
