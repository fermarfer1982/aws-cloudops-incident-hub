# P0 production controls

## Status

- **Reference implementation:** complete in the repository.
- **AWS deployment:** optional and still ephemeral.
- **Production readiness:** **not production-ready** until the remaining P1 controls, business requirements, recovery objectives, ownership and cost governance are approved.

This phase closes the five P0 findings from the repository-based Well-Architected backlog without changing the public GitHub Pages demo or requiring a persistent AWS environment.

## 1. Authentication with Amazon Cognito

The AWS HTTP API uses an Amazon Cognito user pool as its OAuth 2.0 and OpenID Connect issuer. API Gateway validates bearer access tokens through a JWT authorizer before invoking Lambda.

The Cognito app client uses the authorization-code flow and has no client secret, which is suitable for a browser client using PKCE. Self-registration is disabled. Users must be provisioned or federated through an approved identity process before a real deployment.

`GET /health` remains public so load balancers, deployment checks and uptime probes can verify basic service availability without receiving access to incident data.

## 2. Authorization with JWT scopes

The Cognito resource server defines three custom scopes:

| Scope | API operations |
|---|---|
| `cloudops-incident-hub/incidents.read` | `GET /events`, `GET /metrics` |
| `cloudops-incident-hub/incidents.write` | `POST /events` |
| `cloudops-incident-hub/incidents.manage` | `PATCH /events/{incident_id}/status` |

API Gateway enforces the route scopes. The Lambda function is not invoked when a token is missing, invalid, expired, issued by another issuer, intended for another audience, or lacks the required scope.

The app client is authorized to request all three scopes, but real users and applications must be assigned only the scopes needed for their role. A production identity design should normally use separate clients or federation policies for incident producers, readers and operators.

## 3. Explicit CORS allowlist

Wildcard CORS has been removed from:

- API Gateway.
- Lambda environment configuration.
- FastAPI defaults.
- Docker Compose.

The reference allowlist contains the GitHub Pages origin and the known local dashboard origins. CDK contexts can replace the defaults:

```bash
cd infrastructure
cdk synth \
  -c allowed_origins="https://operations.example.com" \
  -c oauth_callback_urls="https://operations.example.com/callback" \
  -c oauth_logout_urls="https://operations.example.com/"
```

Origins must contain only scheme, hostname and optional port. OAuth callback URLs may include a path.

## 4. DynamoDB Query access patterns

The incidents table keeps `incident_id` as its primary key and adds four global secondary indexes:

| Index | Partition key | Sort key | Access pattern |
|---|---|---|---|
| `incidents-by-time` | `entity_type` | `created_at` | Newest incidents across the workload |
| `incidents-by-site` | `site` | `created_at` | Newest incidents for a site |
| `incidents-by-status` | `status` | `created_at` | Newest incidents in a workflow state |
| `incidents-by-severity` | `severity` | `created_at` | Newest incidents by severity |

`GET /events` selects the most relevant index and uses DynamoDB Query with descending sort order. Additional filters are applied only to the bounded result stream returned by the selected partition. No operational DynamoDB Scan remains in the repository or IAM policies.

The API still returns a bounded list and does not yet expose a continuation token. Pagination remains a P2 improvement.

## 5. Transactional incremental metrics

A second DynamoDB table stores materialized counters:

- One global item for total, workflow-status and severity counters.
- One item per site for site totals.

Incident creation performs a DynamoDB transaction containing:

1. A conditional incident write.
2. An increment to global counters.
3. An increment to the site counter.

Because the incident write is conditional, duplicate EventBridge/SQS delivery does not increment metrics twice. Status changes update the incident and the corresponding status counters in one transaction with optimistic concurrency control.

`GET /metrics` reads the global item and queries the `SITE` metric partition. It no longer loads incident records or calculates metrics synchronously.

## Local mode

The local Docker environment does not use Cognito or API Gateway. **Local mode remains unauthenticated** because it is a trusted development laboratory bound to the operator's network. It still uses an explicit CORS allowlist.

The local schema uses new table names:

```text
cloudops-incidents-v2
cloudops-incident-metrics-v2
```

This avoids attempting an in-place GSI migration of the previous DynamoDB Local table. Existing demonstration records remain in the old local table but are not used by version 0.3. Seed new demo data after rebuilding.

## Ephemeral AWS smoke test

The deployment workflow now validates:

1. `GET /health` returns successfully.
2. A protected API route rejects an anonymous request.
3. EventBridge accepts a synthetic event.
4. SQS and Lambda process the event.
5. DynamoDB contains the expected incident.
6. The stack is destroyed and removal is verified.

The workflow injects the synthetic event directly into EventBridge instead of weakening API authentication or storing test user credentials.

## Remaining blockers

Closing WA-001 through WA-005 does not authorize a production launch. The following remain open:

- API throttling, quotas and abuse protection.
- Dependency, code and secret scanning.
- RTO, RPO, PITR and tested restoration.
- SLO, ownership, escalation and alarm routing.
- AWS Budget and anomaly detection.
- Pagination, load testing and empirical tuning.
- Data classification, retention and privacy requirements.
