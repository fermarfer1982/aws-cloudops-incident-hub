# Local performance baseline — 2026-07-10

## Status

**Measured and validated for the local Docker laboratory.**

This record captures observed results from the `mirofish` Ubuntu host running FastAPI and DynamoDB Local through Docker Compose. It is evidence for the local reference environment only; it is not evidence of AWS production capacity.

## Test identification

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Approximate execution window | 12:33–12:35 UTC |
| Commit | `17c6803a73575f892c837e291af0ce9e5676636a` |
| Environment | Ubuntu host `mirofish`, Docker Compose, FastAPI on `localhost:8080`, DynamoDB Local |
| Operator | Repository owner using local account `app` |
| API base URL | `http://localhost:8080` |
| Dataset before mixed test | 9 incidents |
| Dataset after mixed test | 365 incidents |
| Authentication | None; trusted local laboratory only |
| AWS resources used | None |

Host CPU, memory, storage type and concurrent non-test workload were not captured. Those omissions limit comparisons with other machines.

## Commands

### Read-only run 1

```bash
python scripts/run_load_test.py \
  --base-url http://localhost:8080 \
  --duration 30 \
  --concurrency 10 \
  --output artifacts/local-load-test.json
```

### Read-only run 2

```bash
make load-test
```

The Make target executed:

```bash
python scripts/run_load_test.py \
  --base-url http://localhost:8080 \
  --duration 30 \
  --concurrency 10
```

### Mixed run

```bash
python scripts/run_load_test.py \
  --base-url http://localhost:8080 \
  --duration 60 \
  --concurrency 20 \
  --write-percent 5 \
  --output artifacts/local-mixed-load-test.json
```

## Results

| Scenario | Requests | Throughput | Error rate | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| Read-only run 1 | 4,759 | 158.18 req/s | 0.0% | 15.64 ms | 30.49 ms | 38.66 ms |
| Read-only run 2 | 4,795 | 159.38 req/s | 0.0% | 15.22 ms | 29.24 ms | 36.89 ms |
| Mixed, 5% writes | 9,041 | 150.29 req/s | 0.0% | 98.32 ms | 141.59 ms | 162.59 ms |

The two read-only runs differ by less than 1% in throughput, which provides a useful repeatability signal for this host and dataset.

## Provisional gates

| Gate | Target | Observed result | Outcome |
|---|---:|---:|---|
| Maximum error rate | ≤ 1% | 0.0% in all runs | Pass |
| Maximum p95 latency | ≤ 2,000 ms | 30.49 ms read-only; 141.59 ms mixed | Pass |
| HTTP/application failures | 0 unexpected | None observed | Pass |

These gates are engineering thresholds, not an SLA.

## Pagination integrity

After the mixed run, the full dataset was traversed using pages of 100 incidents and the `X-Next-Token` continuation header.

| Check | Result |
|---|---:|
| Pages traversed | 4 |
| Items received | 365 |
| Unique incident IDs | 365 |
| Duplicate IDs | 0 |

Result: **pagination completed without loss or duplication**.

## Aggregate consistency

The metrics endpoint returned:

```json
{
  "total": 365,
  "open": 364,
  "investigating": 1,
  "resolved": 0,
  "critical": 3,
  "warning": 6,
  "info": 356,
  "by_site": {
    "LoadTest": 356,
    "Almeria": 3,
    "Calahorra": 3,
    "Madrid": 3
  }
}
```

The following independent sums match the total of 365:

- Statuses: `364 + 1 + 0 = 365`.
- Severities: `3 + 6 + 356 = 365`.
- Sites: `356 + 3 + 3 + 3 = 365`.

This is evidence that concurrent synthetic writes did not desynchronize the materialized DynamoDB counters in the local run.

## Operational observations

The backend logs were checked for:

```text
ERROR
Traceback
500 Internal
TransactionCanceled
```

No matching errors were found during the test window.

Generated local artifacts:

```text
artifacts/local-load-test.json
artifacts/load-test-report.json
artifacts/local-mixed-load-test.json
```

The `artifacts/` directory remains ignored by Git because raw reports are execution artifacts rather than source-controlled configuration.

## Decision

| Question | Answer |
|---|---|
| Did the local run pass provisional thresholds? | Yes |
| Is the result repeatable on the tested host? | Read-only throughput was repeatable across two runs |
| Is this representative of AWS? | No |
| Should API Gateway throttling change now? | No |
| Should Lambda memory or reserved concurrency change now? | No |
| Should SQS batch size or batching window change now? | No |
| Is another run required? | Yes, against an approved ephemeral AWS environment with cost and traffic controls |

## Scope and limitations

This baseline exercises the synchronous local path:

```text
HTTP client → FastAPI → DynamoDB Local
```

It does not measure:

- Internet latency.
- API Gateway processing and throttling.
- Cognito JWT validation.
- Lambda cold starts, memory pressure or concurrency.
- EventBridge delivery.
- SQS queue age, batching or retries.
- Processor Lambda performance.
- DynamoDB service capacity, throttling or consumed capacity.
- AWS cost per 1,000 incidents.

Accordingly, WA-016 is complete, while WA-017 is complete only for the local laboratory. AWS baseline evidence and WA-018 tuning remain open.