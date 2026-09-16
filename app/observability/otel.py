from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings, get_settings


class TelemetryRuntime:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider: TracerProvider | None = None
        self._httpx_instrumented = False

    def configure(self, app) -> None:
        if not self.settings.otel_enabled or self.provider is not None:
            return
        resource = Resource.create(
            {
                "service.name": self.settings.otel_service_name,
                "deployment.environment": self.settings.app_env,
                "service.version": "0.3.5",
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=self.settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls=self.settings.otel_excluded_urls,
        )
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        self._httpx_instrumented = True
        self.provider = provider

    def shutdown(self) -> None:
        if self._httpx_instrumented:
            HTTPXClientInstrumentor().uninstrument()
            self._httpx_instrumented = False
        if self.provider is not None:
            self.provider.shutdown()
            self.provider = None

    @staticmethod
    def annotate_current_span(**attributes) -> None:
        span = trace.get_current_span()
        if not span.is_recording():
            return
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(f"guilin_ai.{key}", value)


telemetry_runtime = TelemetryRuntime()
