# AWS performance baseline — 2026-07-12

## Status

**Measured and validated for one controlled ephemeral AWS laboratory run.**

This document records the results of a bounded AWS performance experiment against
the real managed-service path. It is evidence for the tested ephemeral profile,
not proof of sustained production capacity.

## Test identification

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| GitHub Actions run | `29185526945` |
| Commit | `0e3310559a53baacb701b08a090dd8acafca9426` |
| Region | `eu-west-1` |
| Environment | Approved ephemeral AWS laboratory |
| Authentication | Cognito OAuth 2.0 client credentials |
| Workflow | `.github/workflows/aws-performance-ephemeral.yml` |
| Stack lifecycle | Deployed, measured, destroyed and removal verified |
| Evidence retention | Sanitized GitHub artifact retained for 14 days |

The account identifier, client secret and bearer token are deliberately excluded
from this repository record.

## Tested path

```text
GitHub Actions
  → Cognito machine access token
  → API Gateway HTTP API
  → Lambda ingestion
  → EventBridge
  → SQS
  → Lambda processor
  → DynamoDB
```

## Configuration

| Parameter | Value |
|---|---:|
| Requested duration | 30 seconds |
| Actual elapsed duration | 30.365 seconds |
| Concurrent workers | 2 |
| Global request-start ceiling | 5 requests/s |
| Synthetic writes | 1% |
| Maximum accepted error rate | 1% |
| Maximum accepted p95 latency | 2,000 ms |

## Client-side results

| Metric | Result |
|---|---:|
| Requests | 152 |
| Successful | 152 |
| Failed | 0 |
| Throughput | 5.01 req/s |
| Error rate | 0.0% |
| p50 | 123.02 ms |
| p95 | 163.59 ms |
| p99 | 216.68 ms |
| Maximum | 264.70 ms |

HTTP responses:

| Status | Count |
|---|---:|
| 200 | 150 |
| 202 | 2 |

## Results by operation

| Operation | Requests | Failed | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| `GET /events` page 1 | 129 | 0 | 104.72 ms | 145.93 ms | 164.63 ms |
| `GET /metrics` | 21 | 0 | 142.37 ms | 203.36 ms | 205.08 ms |
| `POST /events` | 2 | 0 | 166.14 ms | 222.08 ms | 227.06 ms |

All provisional thresholds passed.

## Native AWS metrics

### API Gateway

| Metric | Result |
|---|---:|
| Request count | 156 |
| 4xx responses | 0 |
| 5xx responses | 0 |
| p95 API latency | 88.62 ms |
| p95 integration latency | 51.30 ms |

The API count includes preflight and post-run authenticated verification requests
in addition to the 152 measured load-test samples.

### API Lambda

| Metric | Result |
|---|---:|
| Invocations | 156 |
| Errors | 0 |
| Throttles | 0 |
| p95 duration | 43.24 ms |
| Maximum concurrency | 1 |

### Processor Lambda

| Metric | Result |
|---|---:|
| Invocations | 2 |
| Errors | 0 |
| Throttles | 0 |
| p95 duration | 158.45 ms |
| Maximum concurrency | 1 |

### SQS asynchronous path

| Metric | Result |
|---|---:|
| Messages sent | 2 |
| Messages received | 2 |
| Messages deleted | 2 |

No DLQ activity was observed. CloudWatch returned no datapoints for visible backlog,
oldest-message age or DLQ-visible metrics during the collection window. Missing
datapoints are not interpreted as numeric zero.

### DynamoDB

| Metric | Result |
|---|---:|
| Incident-table write units | 4 |
| Metrics-table read units | 44 |
| Metrics-table write units | 8 |
| Observed read throttles | None |
| Observed write throttles | None |

CloudWatch returned no throttle-event datapoints. The absence of datapoints is
recorded explicitly rather than converted to zero.

## Decision

| Question | Decision |
|---|---|
| Did the controlled AWS baseline pass? | Yes |
| Did the authenticated M2M path work? | Yes |
| Were API or Lambda errors observed? | No |
| Were Lambda throttles observed? | No |
| Did SQS accumulate an observed backlog? | No evidence of backlog in the collection window |
| Did the asynchronous messages complete? | Yes; 2 sent, 2 received and 2 deleted |
| Should API throttling change? | No |
| Should Lambda memory change? | No |
| Should SQS batch or batching-window settings change? | No |
| Should event-source maximum concurrency change? | No |
| Was stack removal verified? | Yes |

The current profile is retained:

- Lambda runtime Python 3.13 on ARM64.
- 256 MB per Lambda.
- No reserved Lambda concurrency.
- SQS batch size 10.
- Maximum batching window 5 seconds.
- SQS event-source maximum concurrency 2.
- API Gateway rate limit 10 requests/s and burst limit 20.

The run did not approach a capacity boundary. Changing these parameters would be
speculative and is therefore rejected.

## Well-Architected outcome

- **WA-017:** completed for the controlled local and AWS laboratory baselines.
- **WA-018:** current settings retained from evidence; comparative tuning remains
  open until a higher traffic objective or a controlled alternative is required.
- **WA-023:** native usage evidence exists, but final billing and cost per 1,000
  incidents remain pending.
- **WA-025:** telemetry exists, but a formal efficiency KPI remains pending.

## Limitations

This run does not prove:

- Sustained behavior beyond 30 seconds.
- Maximum throughput or saturation capacity.
- Performance at the API Gateway throttling boundary.
- Production dataset behavior.
- Multi-tenant behavior.
- Regional recovery.
- WAF or edge-protection behavior.
- Final AWS cost or cost per 1,000 incidents.
- Performance during a larger write-heavy workload.

A broader or comparative test requires a new explicit authorization, cost review
and one controlled parameter change.
