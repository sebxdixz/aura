from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry import context as otel_context
from opentelemetry import propagate
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

_CONFIGURED = False


def setup_telemetry() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    if os.getenv("OTEL_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        _CONFIGURED = True
        return

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "aura-api"),
            "service.version": os.getenv("OTEL_SERVICE_VERSION", "0.5.0"),
            "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "local"),
        }
    )
    provider = TracerProvider(resource=resource)
    mode = os.getenv("OTEL_EXPORTER_MODE", "console").strip().lower()
    if mode == "otlp":
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def get_tracer(name: str = "aura") -> trace.Tracer:
    setup_telemetry()
    return trace.get_tracer(name)


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[Any]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def inject_trace_context(carrier: dict[str, str] | None = None) -> dict[str, str]:
    target = dict(carrier or {})
    propagate.inject(target)
    return target


def attach_trace_context(carrier: dict[str, str] | None) -> object | None:
    if not carrier:
        return None
    extracted = propagate.extract(carrier)
    return otel_context.attach(extracted)


def detach_trace_context(token: object | None) -> None:
    if token is None:
        return
    otel_context.detach(token)


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    return f"{ctx.trace_id:032x}"
