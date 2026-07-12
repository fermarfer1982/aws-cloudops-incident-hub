# ADR-011: Controlled ephemeral AWS performance test

- **Status:** Accepted
- **Date:** 2026-07-10

## Context

The project has a validated local Docker baseline, but that evidence excludes API Gateway, Cognito, Lambda, EventBridge, SQS, managed DynamoDB and AWS service quotas. An AWS measurement is required before changing compute, batching or throttling settings.

A normal unrestricted load test would create avoidable cost and operational risk. The existing deployment workflow already provides OIDC, an ephemeral stack and automatic destruction, but it is designed for smoke testing rather than bounded performance evidence.

## Decision

Create a separate manual GitHub Actions workflow for an ephemeral AWS performance experiment.

The workflow will:

1. Run only from `main` through `workflow_dispatch`.
2. Require exact confirmation plus explicit environment variables for approval and cost-control review.
3. Restrict duration, concurrency, request rate and write percentage to predefined values.
4. Enforce a global request-start ceiling below the deployed API Gateway rate limit.
5. Create an additional Cognito machine client only when `enable_load_test_client=true`.
6. Use the OAuth 2.0 client-credentials grant with read and write scopes, excluding manage access.
7. Use a 15-minute token and mask both the client secret and token.
8. Collect native CloudWatch metrics for API Gateway, Lambda, SQS and DynamoDB.
9. Upload sanitized evidence.
10. Destroy the stack and verify removal regardless of the test result.
11. Fail the workflow when the load test or cleanup does not succeed.

The workflow was prepared in code and executed only after explicit authorization and confirmation of account prerequisites.

## Consequences

### Positive

- AWS performance evidence becomes reproducible and reviewable.
- Traffic and cost exposure are bounded before deployment begins.
- The normal SPA client remains secretless.
- Machine credentials exist only inside the ephemeral stack and runner session.
- Cleanup is part of the acceptance result rather than a best-effort follow-up.
- Tuning decisions can reference both client-side and native service metrics.

### Trade-offs

- Cognito machine-to-machine token requests and the temporary stack can incur charges.
- CloudWatch datapoints can arrive after the collection window.
- The OIDC broker role needs narrow read permissions for the temporary client and CloudWatch metrics.
- One short ephemeral run does not demonstrate sustained production capacity.
- The workflow is more complex than the ordinary smoke-test deployment.

## Rejected alternatives

### Reuse a manually supplied bearer token

Rejected because the token expires quickly, encourages manual secret handling and makes the run difficult to reproduce.

### Disable authentication for the performance route

Rejected because that would measure a security configuration different from the intended AWS architecture.

### Use the normal browser client secretlessly from automation

Rejected because the authorization-code flow requires interactive user authentication and is not suitable for unattended machine testing.

### Run an unrestricted load generator and rely only on API Gateway throttling

Rejected because throttling is a protection mechanism, not a substitute for an explicit traffic ceiling. Intentional 429 responses would also obscure the baseline.

### Retain the stack for later inspection

Rejected because it would weaken the cost and cleanup guarantees of the portfolio laboratory.

## Outcome

The controlled run `29185526945` completed successfully on 2026-07-12:

- 152 successful requests and no failures.
- 5.01 requests/s.
- p95 latency of 163.59 ms.
- No API Gateway 4xx or 5xx responses in the metric window.
- No Lambda errors or throttles.
- Two SQS messages sent, received and deleted.
- Sanitized evidence uploaded.
- Stack removal verified.
- Current compute, batching and throttling settings retained.

Versioned evidence:
`docs/performance-baseline-aws-2026-07-12.md`.

## Remaining follow-up

- Review Cost Explorer after final billing data becomes available.
- Run a controlled comparison only when a higher traffic objective justifies tuning.
