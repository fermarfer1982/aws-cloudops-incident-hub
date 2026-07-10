# Controlled ephemeral AWS performance test

## Status

**Prepared but not executed.**

This runbook defines a bounded AWS performance experiment for the CloudOps Incident Hub. It creates an ephemeral stack, obtains a short-lived machine token, runs a rate-limited test, captures native service metrics, uploads evidence and destroys the stack in the same GitHub Actions job.

The workflow is `.github/workflows/aws-performance-ephemeral.yml`. It has no push, pull-request, schedule or reusable-workflow trigger. It can only be started manually from `main`.

## Purpose

The local Docker baseline proves the synchronous development path:

```text
HTTP client → FastAPI → DynamoDB Local
```

The AWS experiment adds the managed-service path:

```text
GitHub Actions
  → Cognito client-credentials token
  → API Gateway HTTP API
  → Lambda ingestion
  → EventBridge
  → SQS
  → Lambda processor
  → DynamoDB
```

The result is evidence for one ephemeral laboratory run. It is not proof of sustained production capacity.

## Mandatory governance gates

The GitHub environment `aws-ephemeral` must contain these variables:

| Variable | Required value | Purpose |
|---|---|---|
| `AWS_REGION` | Approved AWS Region | Limits deployment scope |
| `AWS_ACCOUNT_ID` | Approved laboratory account | Prevents deployment to another account |
| `AWS_DEPLOY_ROLE_ARN` | OIDC deployment role ARN | Uses temporary STS credentials |
| `AWS_LOAD_TEST_APPROVED` | `true` | Records explicit authorization for the run |
| `AWS_COST_CONTROLS_CONFIRMED` | `true` | Confirms budget and anomaly alerts were reviewed |

The environment should require a human reviewer. Do not set the two approval variables permanently for an unattended account.

The operator must enter exactly:

```text
RUN-EPHEMERAL-AWS-PERFORMANCE-TEST
```

## Hard traffic limits

The workflow exposes only these choices:

| Control | Allowed values | Maximum |
|---|---|---:|
| Duration | 15, 30 or 60 seconds | 60 seconds |
| Concurrency | 1, 2 or 5 workers | 5 |
| Global request starts | 1, 2, 5 or 8 requests/s | 8 requests/s |
| Synthetic writes | 0%, 1% or 5% | 5% |

The default API Gateway throttling limit is 10 requests/s with a burst of 20. The workflow rejects a selected `max_rps` that is greater than or equal to the deployed rate limit.

The request ceiling is global across all workers and includes second-page requests. It is enforced by `scripts/run_load_test.py --max-rps`; concurrency alone is not treated as a traffic limit.

## Temporary authentication

The normal web client remains a public authorization-code client without a secret.

Only when CDK receives:

```text
enable_load_test_client=true
```

the stack creates an additional machine client with:

- `client_credentials` as its only OAuth grant.
- A generated client secret.
- Read and write incident scopes only.
- A 15-minute access token.
- No manage scope.

The workflow reads the generated secret with `DescribeUserPoolClient`, masks both the secret and access token, and never uploads either value as evidence. The client is deleted with the stack.

## Execution sequence

1. Validate exact confirmation, environment approvals and bounded choices.
2. Acquire temporary AWS credentials through GitHub OIDC.
3. Run tests, CDK synthesis and every repository guardrail.
4. Deploy the ephemeral profile with the temporary machine client.
5. Request a 15-minute Cognito access token.
6. Verify an authenticated read against `GET /events`.
7. Run the bounded load test with provisional gates:
   - Error rate no greater than 1%.
   - p95 latency no greater than 2,000 ms.
8. Capture protected API state after the test.
9. Wait for CloudWatch metric ingestion and collect native metrics.
10. Destroy the stack regardless of test outcome.
11. Verify CloudFormation no longer reports the stack.
12. Upload sanitized evidence for 14 days.
13. Mark the workflow failed when the load test, destroy or cleanup verification fails.

## Native metrics collected

The collector `scripts/collect_aws_performance_evidence.py` records:

### API Gateway

- Request count.
- 4xx and 5xx responses.
- p95 total latency.
- p95 integration latency.

### Lambda

For both ingestion and processor functions:

- Invocations.
- Errors.
- Throttles.
- p95 duration.
- Maximum concurrent executions.

### SQS

- Messages sent, received and deleted.
- Maximum visible backlog.
- Maximum oldest-message age.
- Maximum DLQ visible messages.

### DynamoDB

For the incident and metric tables:

- Consumed read capacity units.
- Consumed write capacity units.
- Read throttle events.
- Write throttle events.

CloudWatch metrics can arrive after the collection window. Missing datapoints are recorded explicitly instead of being converted to zero.

## Evidence artifact

The artifact name is:

```text
aws-performance-evidence-<github-run-id>
```

Expected sanitized files include:

```text
cdk-outputs.json
execution-metadata.json
token-metadata.json
authenticated-read.json
aws-load-test-report.json
application-metrics.json
incidents-page.json
aws-service-metrics.json
cleanup-status.txt
```

No access token or client secret belongs in the artifact.

## Cost controls and limitations

The workflow can generate AWS charges for API Gateway, Lambda, Cognito machine-to-machine token requests, EventBridge, SQS, DynamoDB and CloudWatch. The hard duration and rate ceilings constrain the experiment but do not guarantee a zero-cost run.

AWS billing data is not available in real time. Review Cost Explorer and the configured budget after billing data has been ingested. Do not infer cost per 1,000 incidents from list prices without recording Region, free-tier status, account discounts and actual service usage.

The experiment does not validate:

- Long-duration stability.
- Production quotas or multi-tenant behavior.
- Regional failover.
- Real user authentication traffic.
- WAF or edge protection.
- A production data volume.

## Decision rules after a run

Do not change Lambda memory, reserved concurrency, SQS batch size, batching window or API throttling merely because the workflow completed.

A tuning proposal must cite:

- The load-test JSON report.
- Native CloudWatch evidence.
- Error and throttle counts.
- Queue age and backlog.
- Dataset and traffic mix.
- A comparison run with one controlled parameter changed.
- Cost implications.

Until an approved run exists, WA-017 remains open for AWS evidence and WA-018 remains open for empirical tuning.
