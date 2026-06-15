# chapter-03/catalog-service/main.py
import random, time
from fastapi import FastAPI, Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

app = FastAPI()

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


def simulate(error_rate=0.01, mu=-2.8, sigma=0.5):
    time.sleep(max(0.005, random.lognormvariate(mu, sigma)))
    if random.random() < error_rate:
        raise RuntimeError("upstream error")


@app.get("/catalog")
def get_catalog():
    handler = "/catalog"
    start = time.perf_counter()
    try:
        simulate()
        REQUEST_COUNT.labels(handler=handler, method="GET", status_code="200").inc()
        return {"items": random.randint(10, 500)}
    except RuntimeError as e:
        REQUEST_COUNT.labels(handler=handler, method="GET", status_code="500").inc()
        REQUEST_ERRORS.labels(handler=handler).inc()
        return Response(str(e), status_code=500)
    finally:
        REQUEST_DURATION.labels(handler=handler).observe(time.perf_counter() - start)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
