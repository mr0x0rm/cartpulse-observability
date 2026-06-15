# chapter-03/search-service/main.py
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
    "http_requests_total", "Total HTTP requests", ["handler", "method", "status_code"]
)
REQUEST_ERRORS = Counter(
    "http_request_errors_total", "Total HTTP 5xx errors", ["handler"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    ["handler"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


def simulate():
    # Search is CPU-heavier: slightly higher latency, very low error rate
    time.sleep(max(0.005, random.lognormvariate(-2.3, 0.6)))
    if random.random() < 0.005:
        raise RuntimeError("index unavailable")


@app.get("/search")
def search():
    handler = "/search"
    start = time.perf_counter()
    try:
        simulate()
        REQUEST_COUNT.labels(handler=handler, method="GET", status_code="200").inc()
        return {"results": random.randint(0, 200)}
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
