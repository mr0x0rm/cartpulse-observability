# chapter-06/apps/cartpulse/checkout-service/main.py
import random
import time
import os
from fastapi import FastAPI, Response

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

# ── OpenTelemetry SDK setup ───────────────────────────────────────────────────
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Resource — describes this process, not individual spans
# service.name is a Resource attribute, NOT a span attribute
resource = Resource.create(
    {
        ResourceAttributes.SERVICE_NAME: "checkout-service",
        ResourceAttributes.SERVICE_VERSION: os.environ.get("SERVICE_VERSION", "0.1.0"),
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.environ.get(
            "ENVIRONMENT", "local"
        ),
        # K8s attributes will be added by the OTel Collector via resource detection
        # We don't set k8s.pod.name here — the Collector reads it from the node
    }
)

# OTLP exporter — sends to OTel Collector DaemonSet on the same node
# OTEL_EXPORTER_OTLP_ENDPOINT is injected via Kubernetes env var
otlp_endpoint = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://localhost:4317",  # fallback for local development
)

exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

app = FastAPI()

# Auto-instrument FastAPI — captures every HTTP request as a SERVER span
# SpanKind.SERVER is set automatically by the instrumentor
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument requests library — captures outbound HTTP as CLIENT spans
# (used when checkout calls payments-service)
RequestsInstrumentor().instrument()

# ── Prometheus metrics (unchanged from previous chapters) ─────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["handler", "method", "status_code"],
)
REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total HTTP 5xx errors",
    ["handler"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    ["handler"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
ACTIVE_CHECKOUTS = Gauge(
    "checkout_active_requests",
    "Number of checkout requests currently in progress",
)

DEGRADED = os.environ.get("DEGRADED", "false").lower() == "true"


def simulate_checkout_processing():
    """Simulate checkout with child spans to show the waterfall."""
    # Create explicit child spans to show where time is spent
    # In a real service these would wrap actual DB/Redis/HTTP calls
    with tracer.start_as_current_span(
        "checkout.validate_cart",
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        latency = random.uniform(0.005, 0.020)
        time.sleep(latency)
        span.set_attribute("cart.items_count", random.randint(1, 10))

    with tracer.start_as_current_span(
        "checkout.reserve_inventory",
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        if DEGRADED:
            # Simulate slow inventory lock — this is what the March incident looked like
            latency = random.uniform(0.5, 2.0)
            time.sleep(latency)
            span.set_attribute("inventory.lock_wait_ms", int(latency * 1000))
            span.set_attribute("inventory.degraded", True)
            if random.random() < 0.6:
                span.set_status(trace.StatusCode.ERROR, "inventory lock timeout")
                raise RuntimeError("inventory lock timeout")
        else:
            time.sleep(random.uniform(0.010, 0.040))
            span.set_attribute("inventory.lock_wait_ms", random.randint(10, 40))

    with tracer.start_as_current_span(
        "checkout.process_payment",
        kind=trace.SpanKind.CLIENT,  # CLIENT because this calls an external gateway
    ) as span:
        latency = random.lognormvariate(-2.0, 0.4)
        latency = max(0.020, min(latency, 0.300))
        time.sleep(latency)
        span.set_attribute("payment.gateway", "stripe")
        span.set_attribute("payment.duration_ms", int(latency * 1000))


# ── Endpoints ──────────────────────────────────────────────────────────────────


@app.post("/checkout")
def process_checkout():
    handler = "/checkout"
    ACTIVE_CHECKOUTS.inc()
    start = time.perf_counter()
    try:
        simulate_checkout_processing()
        status = "200"
        REQUEST_COUNT.labels(handler=handler, method="POST", status_code=status).inc()
        return {
            "status": "ok",
            "order_id": f"ord-{random.randint(10000, 99999)}",
        }
    except RuntimeError as e:
        status = "500"
        REQUEST_COUNT.labels(handler=handler, method="POST", status_code=status).inc()
        REQUEST_ERRORS.labels(handler=handler).inc()
        return Response(content=str(e), status_code=500)
    finally:
        REQUEST_DURATION.labels(handler=handler).observe(time.perf_counter() - start)
        ACTIVE_CHECKOUTS.dec()


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
