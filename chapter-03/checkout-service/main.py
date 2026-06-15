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

app = FastAPI()

"""-----------------------------------------Metrics--------------------------------------------
Three Metrics, chosen to answer Mihail's three questions:
    1. http_request_total:              - is it responding? ( Availibility via up metric
    2. http_request_errors_total:       - are requests succeeding? (error rate)
    3. http_request_duration_seconds:   - how long is it taking? (latency)

# Label discipline: only low-cardinality values.
            GOOD: handler="/checkout", method="POST", status_code="200"
            BAD:  user_id="1234" <- unbounded, will cause cardinality explosion
"""

REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Total number of HTTP requests received",
    ["handler", "method", "status_code"],
)

REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total number of failed HTTP requests",
    ["handler"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["handler"],
    # Explicit buckets matching CartPulse's latency SLO targets (set in Ch 8)
    # Bucket design principle: cover expected p50 (0.05s), p95 (0.5s), p99 (1s)
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# A gauge for in-flight checkouts - useful for spotting connection pool saturation
# ( the root cause of the March 14 incident )
ACTIVE_CHECKOUTS = Gauge(
    "checkout_active_requests",
    "Number of active checkout requests currently in progress",
)

"""-----------------------------------------Simulated service behaviour--------------------------------------------
This simulates a checkout service with realistic behaviour:
    - Baseline p50 latency ~80ms, p99 ~400ms
    - 2% error rate under normal conditions
    - Occasional latency spikes (simulating connection pool pressure)
    - An injectable "degraded mode" via the DEGRADED env var
    
This is not a toy. It models the failure mode from March 14.
----------------------------------------------------------------------------------------------------------------"""
DEGRADED = os.getenv("DEGRADED", "false").lower() == "true"


def simulate_checkout_processing():
    """Simulate checkout with latency distribution"""
    if DEGRADED:
        # Simulate connection pool exhaustion: requests hang 0.5-3s
        time.sleep(random.uniform(0.5, 3.0))
        if random.random() < 0.6:  # 50% error rate when degraded
            raise RuntimeError("Connection pool exhausted")
    else:
        # Normal operation: lognormal latency centred at ~80ms
        latency = random.lognormvariate(mu=-2.5, sigma=0.8)
        latency = max(0.005, min(latency, 2.0))  # clamp to [5ms, 2s
        time.sleep(latency)
        if random.random() < 0.02:  # 2% error rate
            raise RuntimeError("downstream service unavailable ")


# -------------------------------------- Endpoints --------------------------------------------


@app.post("/checkout")
def process_checkout():
    handler = "/checkout"
    ACTIVE_CHECKOUTS.inc()
    start = time.perf_counter()
    try:
        simulate_checkout_processing()
        status = "200"
        REQUEST_COUNTER.labels(handler=handler, method="POST", status_code=status).inc()
        return {"status": "ok", "order_id": f"ord-{random.randint(10000, 99999)}"}
    except RuntimeError as e:
        status = "500"
        REQUEST_COUNTER.labels(handler=handler, method="POST", status_code=status).inc()
        REQUEST_ERRORS.labels(handler=handler).inc()
        return Response(content=str(e), status_code=500)
    finally:
        duration = time.perf_counter() - start
        REQUEST_DURATION.labels(handler=handler).observe(duration)
        ACTIVE_CHECKOUTS.dec()


@app.get("/health")
def health():
    """Kubernetes-style health endpoint. Not instrumented — Prometheus uses /metrics."""
    return {"status": "healthy"}


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint. Returns all registered metrics in exposition format."""
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
