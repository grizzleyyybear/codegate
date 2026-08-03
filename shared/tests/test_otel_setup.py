from opentelemetry import trace

from shared.otel_setup import setup_otel


def test_setup_otel_sets_provider_and_returns_tracer():
    tracer = setup_otel("codegate-test-service")
    assert tracer is not None
    assert isinstance(tracer, trace.Tracer)
    provider = trace.get_tracer_provider()
    assert provider is not None


def test_setup_otel_default_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracer = setup_otel("codegate-test-default")
    assert tracer is not None
