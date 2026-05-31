"""
Observability for GOOPHER — structured logging, tracing, and lightweight metrics.

Design goals:
  * Built in, not bolted on: every agent turn and tool call is traced.
  * Zero external deps to run locally (console exporter).
  * One env flag (`otel_exporter=gcp`) flips to Google Cloud Trace / Logging
    on Cloud Run, all within the GCP free tier.

We use OpenTelemetry's API so spans are vendor-neutral. If the OTel packages
aren't installed (e.g. minimal CI), we fall back to a no-op tracer so the app
still runs.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from ..config import get_settings

_settings = get_settings()


# --------------------------------------------------------------------------- #
# Structured JSON logging (Cloud Logging parses JSON lines automatically)
# --------------------------------------------------------------------------- #
class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)  # type: ignore[attr-defined]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("goopher")
    if logger.handlers:  # already configured
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(_settings.log_level.upper())
    logger.propagate = False
    return logger


log = configure_logging()


def log_event(message: str, **fields: Any) -> None:
    """Emit a structured log line with arbitrary context fields."""
    record = logging.LogRecord("goopher", logging.INFO, "", 0, message, None, None)
    record.extra_fields = fields  # type: ignore[attr-defined]
    log.handle(record)


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #
def _init_tracer():
    """Try to build a real OTel tracer; fall back to None (no-op) on any error."""
    if not _settings.enable_tracing:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        resource = Resource.create({"service.name": "goopher-agent"})
        provider = TracerProvider(resource=resource)

        if _settings.otel_exporter == "gcp":
            # Cloud Trace exporter (free tier: 2.5M spans/month).
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter(project_id=_settings.google_cloud_project)
        else:
            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        return trace.get_tracer("goopher")
    except Exception as exc:  # pragma: no cover - optional dependency path
        log_event("tracing_disabled", reason=str(exc))
        return None


_tracer = _init_tracer()

# Simple in-process metric counters, exposed at /metrics for scraping.
METRICS: dict[str, float] = {
    "chat_requests_total": 0,
    "tool_calls_total": 0,
    "errors_total": 0,
    "tokens_estimated_total": 0,
}


def incr(metric: str, value: float = 1) -> None:
    METRICS[metric] = METRICS.get(metric, 0) + value


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[str]:
    """
    Context manager that opens a trace span and yields a trace id.

    Works whether or not OTel is installed: always yields a usable id and
    always emits a structured timing log, so observability degrades gracefully.
    """
    trace_id = uuid.uuid4().hex
    start = time.perf_counter()
    if _tracer is not None:
        with _tracer.start_as_current_span(name) as otel_span:
            for k, v in attrs.items():
                otel_span.set_attribute(k, v)
            ctx = otel_span.get_span_context()
            trace_id = format(ctx.trace_id, "032x") if ctx and ctx.trace_id else trace_id
            try:
                yield trace_id
            finally:
                _emit_span_log(name, start, trace_id, attrs)
    else:
        try:
            yield trace_id
        finally:
            _emit_span_log(name, start, trace_id, attrs)


def _emit_span_log(name: str, start: float, trace_id: str, attrs: dict) -> None:
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    log_event("span", span=name, trace_id=trace_id, elapsed_ms=elapsed_ms, **attrs)
