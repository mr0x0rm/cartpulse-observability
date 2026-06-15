# chapter-05/golden-path/new-service-checklist.md
# CartPulse — New Service Observability Checklist (v1)

Every service deployed to the cartpulse namespace must satisfy
all items before being considered production-ready.

## Metrics
- [ ] Service exposes /metrics endpoint in Prometheus exposition format
- [ ] Metric names follow convention: http_requests_total, http_request_errors_total,
      http_request_duration_seconds
- [ ] All label values are low-cardinality (no user_id, request_id, email)
- [ ] A ServiceMonitor CR exists in the cartpulse namespace
- [ ] Service appears as a healthy target in Prometheus (/targets)

## Alerting
- [ ] At minimum: availability alert (up == 0) configured
- [ ] At minimum: error rate alert (> 5% for 2m) configured
- [ ] All alerts have runbook annotations
- [ ] Alerts have been tested by intentionally triggering them

## Dashboards
- [ ] Service appears on the CartPulse Service Overview dashboard
- [ ] p95 latency, error rate, and request rate panels exist

## Operational
- [ ] /health endpoint returns 200 when service is ready
- [ ] Readiness and liveness probes configured in deployment
- [ ] Resource requests and limits set (no unbounded containers)
- [ ] On-call runbook written and linked from service documentation
