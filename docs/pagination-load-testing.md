# Cursor pagination and reproducible load testing

## Scope

This phase removes the fixed one-response listing assumption and adds a repeatable way to measure the API without deploying AWS resources.

It provides:

- DynamoDB cursor pagination based on `LastEvaluatedKey` and `ExclusiveStartKey`.
- An opaque, URL-safe continuation token bound to the active filters and selected index.
- A non-breaking list response: `GET /events` still returns a JSON array.
- The next cursor in the `X-Next-Token` response header.
- Browser access to that header through explicit CORS exposure.
- A bounded asynchronous load-test harness that writes a JSON evidence artifact.

## API contract

First page:

```bash
curl -i "http://localhost:8080/events?limit=25"
```

When another page exists, the response includes:

```text
X-Next-Token: <opaque-token>
```

Request the next page:

```bash
curl -i --get "http://localhost:8080/events" \
  --data-urlencode "limit=25" \
  --data-urlencode "next_token=<opaque-token>"
```

The token is valid only with the same combination of:

- `site`
- `status`
- `severity`
- selected DynamoDB index

Reusing it with different filters returns HTTP `400`.

## Token properties

The token is:

- URL-safe Base64.
- Versioned.
- Schema-validated.
- Limited to 4,096 characters.
- Bound to the query context.
- Free of credentials and incident payloads.

The token is opaque to clients but is not an authorization mechanism or an encrypted secret. API Gateway authentication and scopes remain the security boundary.

## DynamoDB behavior

Each HTTP page performs one bounded DynamoDB `Query` operation. The returned `LastEvaluatedKey`, when present, becomes the next continuation token.

A page can contain fewer items than `limit` when additional filters are evaluated by DynamoDB after reading candidate items. A non-empty `X-Next-Token` means the client can continue.

The implementation does not use DynamoDB `Scan`.

## Dashboard compatibility

The local dashboard follows `X-Next-Token` automatically. It requests pages of 100 incidents and applies defensive caps of:

- 1,000 incidents.
- 20 pages.

These caps protect the browser demonstration; they are not API limits.

## Local load test

Install the existing development dependencies and start Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt

docker compose up -d --build
bash scripts/seed_demo.sh
```

Run a read-only baseline:

```bash
python3 scripts/run_load_test.py \
  --base-url http://localhost:8080 \
  --duration 60 \
  --concurrency 20 \
  --output artifacts/local-load-test.json
```

The default traffic mix is:

- 80% paginated incident reads.
- 20% metric reads.
- 0% writes.

Enable a small synthetic write percentage explicitly:

```bash
python3 scripts/run_load_test.py \
  --duration 60 \
  --concurrency 20 \
  --write-percent 5 \
  --output artifacts/local-mixed-load-test.json
```

Synthetic writes use site `LoadTest` and event type `LOAD_TEST_EVENT`.

## Protected AWS endpoint

A cloud test requires a valid Cognito access token with the required scopes:

```bash
export LOAD_TEST_BASE_URL="https://example.execute-api.eu-west-1.amazonaws.com"
export LOAD_TEST_BEARER_TOKEN="<access-token>"

python3 scripts/run_load_test.py \
  --duration 60 \
  --concurrency 10 \
  --output artifacts/aws-load-test.json
```

Do not run load tests against AWS without explicit approval, cost controls, a defined traffic ceiling and a cleanup plan.

## Evidence produced

The JSON report contains:

- Total, successful and failed requests.
- Error rate.
- Requests per second.
- p50, p95 and p99 latency.
- Status-code distribution.
- Per-operation latency and failures.
- Up to 50 failed samples.
- Threshold results.

Default provisional thresholds:

```text
Maximum error rate: 1%
Maximum p95 latency: 2,000 ms
```

These are engineering gates aligned with the provisional SLO. They are not a contractual SLA and must be recalibrated using representative traffic.

## Current evidence status

The harness, pagination tests and CloudFormation controls are implemented in the repository. A representative baseline has not yet been executed and approved, so WA-017 and WA-018 remain operationally open.
