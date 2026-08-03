"""One-line OpenTelemetry bootstrap every service calls at startup.

Usage:
    from shared.otel_setup import setup_otel
    tracer = setup_otel(service_name="codegate-validator")

Each agent hop (plan, retrieve, generate, validate, gate) should open its
own span so Grafana can show per-stage latency and the pipeline's overall
shape, not just per-HTTP-request timing.
"""
from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_otel(service_name: str) -> trace.Tracer:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
