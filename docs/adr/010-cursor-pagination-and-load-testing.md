# ADR-010: Cursor pagination and reproducible load testing

- Status: Accepted
- Date: 2026-07-10
- Decision owners: CloudOps architecture and application engineering

## Context

`GET /events` previously attempted to collect up to the requested limit by following DynamoDB pages internally. That approach hid DynamoDB pagination from clients, increased work per request and provided no stable continuation contract.

The project also had provisional latency and availability objectives but no repository-owned tool for producing repeatable performance evidence.

## Decision

### Pagination

Use DynamoDB `LastEvaluatedKey` as the server-side cursor and expose it to clients as a versioned, URL-safe opaque token.

The public contract remains backwards-compatible:

- Response body remains a JSON array.
- `X-Next-Token` is present only when another page exists.
- Clients pass the token back through `next_token`.
- Tokens are bound to the selected index and active filters.
- Invalid, malformed or mismatched tokens return HTTP 400.
- API Gateway and FastAPI explicitly expose `X-Next-Token` through CORS.

Each API page performs one bounded DynamoDB Query. No Scan is introduced.

### Load testing

Maintain a small asynchronous Python harness in the repository rather than introducing a separate load-testing platform for the laboratory.

The harness:

- Uses the existing `httpx` development dependency.
- Supports local and authenticated cloud endpoints.
- Is read-only by default.
- Requires explicit configuration before generating synthetic writes.
- Produces a versioned JSON report.
- Enforces provisional p95 and error-rate thresholds.
- Does not run automatically against AWS.

## Alternatives considered

### Return a new response envelope

A response such as `{ "items": [...], "next_token": "..." }` is conventional but would break the current dashboard and existing clients. The response header preserves compatibility while still exposing pagination.

### Keep auto-pagination inside one request

Rejected because request cost and latency grow with the number of DynamoDB pages, and clients cannot control incremental retrieval.

### Expose DynamoDB keys directly

Rejected because it couples clients to the physical table and index schema. The token remains opaque and versioned.

### Add WAF or a managed load-testing service now

Rejected for this phase. WAF requires an approved threat model and edge design. Managed performance environments can create persistent cost and are unnecessary for establishing a local reproducible baseline.

### Use Locust or k6

Both are valid future options. A repository-local Python harness was selected because it reuses installed dependencies, has no additional service lifecycle and can emit exactly the evidence schema required by this project.

## Consequences

Positive:

- Listing cost is bounded per request.
- Clients can retrieve incrementally.
- Filter misuse and malformed tokens fail explicitly.
- The browser dashboard remains compatible.
- Performance evidence can be generated consistently.

Trade-offs:

- A filtered DynamoDB page can contain fewer items than the requested limit.
- The token is opaque but not encrypted and must not contain secrets.
- The local harness is not a distributed load generator.
- Thresholds remain provisional until representative tests are executed.

## Production gate

This decision completes the reference implementation for WA-016. WA-017 and WA-018 remain open until a representative test is executed, evidence is reviewed and compute, concurrency, batching and throttling settings are justified by measurements.

## Subsequent outcome

[ADR-011](011-controlled-ephemeral-aws-performance-test.md) subsequently defined
and executed the controlled ephemeral AWS baseline. WA-017 is complete for the
controlled local and AWS laboratory baselines. The measured evidence supported
retaining the current settings. WA-018 remains conditional on a real higher-scale
traffic objective and a controlled tuning comparison; it is not closed by the
short laboratory run.
