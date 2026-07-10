# AWS Well-Architected Review

## Review metadata

- **Workload:** AWS CloudOps Incident Hub
- **Review type:** Repository-based self-assessment
- **Review date:** 2026-07-10
- **Reviewer:** Fernando Martínez Fernández
- **Framework:** AWS Well-Architected Framework, six pillars
- **Environment assessed:** Local zero-cost laboratory plus the proposed ephemeral AWS architecture
- **Production readiness:** Not production-ready

> This document is a technical self-assessment, not an AWS Well-Architected Tool review and not an external audit. Findings are based on evidence versioned in this repository. A control marked as completed in the reference implementation still requires deployment evidence and operational validation before production use.

## Scope and assumptions

The workload receives infrastructure incidents and processes them through API Gateway, Lambda, EventBridge, SQS, a Dead Letter Queue, DynamoDB and CloudWatch. The AWS reference now includes Amazon Cognito, JWT route scopes, explicit CORS origins, query-oriented DynamoDB indexes and transactional metric aggregates.

The local implementation uses Docker, FastAPI and DynamoDB Local. Local mode deliberately remains unauthenticated inside the trusted development network. The public GitHub Pages dashboard contains demonstration data only.

No persistent production traffic profile, RTO, RPO, SLO, compliance regime, data classification or formal ownership model has been approved. A real AWS deployment may incur charges.

## Rating model

| Rating | Meaning |
|---|---|
| Low risk | Controls are appropriate for the current scope; minor improvements remain. |
| Medium risk | Important controls exist, but one or more material gaps remain. |
| High risk | A production launch would expose an unacceptable failure, security or governance risk. |
| Not assessed | Evidence or requirements are insufficient for a defensible conclusion. |

## Executive summary

| Pillar | Current rating | Main strength | Main risk |
|---|---|---|---|
| Operational excellence | Medium | IaC, CI, runbooks, smoke evidence and cleanup | No approved SLO, ownership or alert-routing process |
| Security | Medium for production reference | Cognito JWT scopes, OIDC federation, explicit CORS and least privilege | No abuse protection, data classification or supply-chain security baseline |
| Reliability | Medium | EventBridge, SQS, DLQ, retries, idempotency and alarms | No approved RTO/RPO, restore test or regional recovery strategy |
| Performance efficiency | Medium | Query-oriented indexes, incremental metrics, ARM64 and batching | No pagination contract, load test or empirical tuning |
| Cost optimization | Low for laboratory / Medium for production | Ephemeral lifecycle and cost guardrails | No AWS Budget, anomaly detection or measured unit economics |
| Sustainability | Low for laboratory / Medium for production | Ephemeral resources, managed services and query access patterns | No utilization baseline or sustainability KPI |

### Overall conclusion

WA-001 through WA-005 are closed in the reference implementation: the cloud API is authenticated and scope-authorized, CORS is explicit, operational listings use DynamoDB Query and metrics are materialized transactionally. The workload remains **not production-ready** because recovery objectives, tested restore, SLOs, ownership, alarm routing, financial controls, abuse protection and workload evidence are still missing.

---

# 1. Operational excellence

## Evidence

- AWS CDK defines the cloud architecture.
- GitHub Actions runs linting, tests, CDK synthesis and all guardrails.
- Deployment uses GitHub OIDC, explicit confirmation, smoke tests and automatic destroy.
- CloudWatch dashboards, alarms, runbooks, ADRs and temporary evidence are versioned.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| OPS-01 | No approved service owner, escalation path or on-call responsibility | High | Open |
| OPS-02 | No SLO, error budget, availability target or latency objective | High | Open |
| OPS-03 | Alarms have no notification or incident-management destination | Medium | Accepted for laboratory |
| OPS-04 | No game-day or failure-injection evidence | Medium | Open |
| OPS-05 | No formal release and rollback decision procedure | Medium | Open |

## Recommended actions

Define workload ownership and measurable SLOs, route alarms to an approved channel, execute game days and document release/rollback criteria.

## Pillar rating

**Medium risk.** Engineering automation is strong, but operational accountability and measurable outcomes remain undefined.

---

# 2. Security

## Evidence

- GitHub Actions uses OIDC and temporary STS credentials.
- API Gateway uses a Cognito JWT authorizer.
- Custom scopes separate read, write and manage operations.
- Only `GET /health` is public in AWS.
- CORS uses an explicit allowlist.
- DynamoDB and SQS use managed encryption, and Lambda policies exclude `dynamodb:Scan`.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SEC-01 | API Gateway endpoint has no authentication or authorization | Critical | Closed in reference implementation |
| SEC-02 | CORS allows every origin | High | Closed in reference implementation |
| SEC-03 | No WAF decision, throttling policy, request quota or abuse protection | High | Open |
| SEC-04 | No formal data classification, retention policy or privacy assessment | High | Open |
| SEC-05 | No dependency vulnerability scanning, secret scanning policy or SBOM | Medium | Open |
| SEC-06 | Effective CDK bootstrap-role permissions require separate review | Medium | Open |
| SEC-07 | Central CloudTrail, GuardDuty and Security Hub remain target-state controls | Medium | Deferred to landing zone implementation |

## Recommended actions

Validate federation and client separation in the target environment, add throttling and abuse controls, define data governance, and establish dependency, code, secret and SBOM controls.

## Pillar rating

**Medium risk for the production reference.** Authentication, authorization and CORS blockers are closed in code, but production identity operations, abuse protection and governance evidence are not yet complete.

---

# 3. Reliability

## Evidence

- EventBridge decouples ingestion from processing.
- SQS provides durable buffering, retries and partial batch failure handling.
- A DLQ retains poison messages.
- Conditional writes and deterministic identifiers provide idempotency.
- Transactional counters keep incident and metric changes consistent.
- Queue-age, Lambda-error and DLQ alarms are defined.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| REL-01 | RTO and RPO are undefined | High | Open |
| REL-02 | DynamoDB PITR and backup policy are not enabled | High | Accepted for ephemeral laboratory only |
| REL-03 | Restore procedures have not been tested | High | Open |
| REL-04 | Architecture is single-region with no approved recovery strategy | Medium | Open |
| REL-05 | Client timeout, retry and backoff behavior are not documented | Medium | Open |
| REL-06 | Poison-message and redrive integration evidence is incomplete | Medium | Open |
| REL-07 | Alarm notifications are not routed to responders | Medium | Accepted for laboratory |

## Recommended actions

Define RTO/RPO, enable PITR for persistent environments, test restore and regional recovery, and execute failure scenarios with real notification paths.

## Pillar rating

**Medium risk.** Failure isolation is strong, but business recovery objectives and restore evidence are absent.

---

# 4. Performance efficiency

## Evidence

- Lambda uses ARM64, bounded memory and reserved concurrency.
- SQS processing uses batches and a batching window.
- The incidents table has GSIs for time, site, status and severity.
- `GET /events` uses DynamoDB Query rather than Scan.
- Metrics are maintained as transactional incremental aggregates.
- Lambda duration and throttling metrics are available.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| PERF-01 | `GET /events` uses DynamoDB Scan and in-memory filtering | High at scale | Closed in reference implementation |
| PERF-02 | Metrics scan and aggregate incident records synchronously | High at scale | Closed in reference implementation |
| PERF-03 | No load test, throughput objective or representative traffic model | High | Open |
| PERF-04 | Reserved concurrency of two may throttle legitimate bursts | Medium | Intentional laboratory guardrail |
| PERF-05 | Memory, timeout and batch settings lack empirical tuning | Medium | Open |
| PERF-06 | No continuation-token pagination contract is exposed | Medium | Open |

## Recommended actions

Add opaque continuation tokens, run representative load tests, inspect hot partitions and tune Lambda concurrency, memory and SQS batch settings from measurements.

## Pillar rating

**Medium risk.** The primary Scan bottlenecks are removed, but scale behavior has not been measured and pagination remains incomplete.

---

# 5. Cost optimization

## Evidence

- Local mode and GitHub Pages do not require AWS runtime resources.
- AWS deployment is manual, temporary and automatically destroyed.
- Static guardrails reject high-risk fixed-cost resources.
- DynamoDB uses on-demand capacity and Lambda compute is bounded.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| COST-01 | No AWS Budget, anomaly monitor or billing alarm is defined | High before real deployment | Open |
| COST-02 | Cost allocation tags are incomplete | Medium | Open |
| COST-03 | No cost-per-incident model exists | Medium | Open |
| COST-04 | CDK bootstrap resources may remain after stack destruction | Medium | Documented |
| COST-05 | CloudWatch and Cognito usage may incur charges in a real account | Medium | Documented |
| COST-06 | Emergency cleanup depends on the federated role and GitHub availability | Medium | Accepted risk |

## Recommended actions

Configure account-level budgets and anomaly detection before deployment, complete tagging, estimate cost per 1,000 incidents and inventory orphaned resources.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** Lifecycle controls are strong, but financial governance is not implemented.

---

# 6. Sustainability

## Evidence

- The workload is not kept running in AWS by default.
- Managed serverless services scale with demand.
- Lambda uses ARM64 and SQS batching.
- Query-based access and incremental metrics avoid repeated table scans.
- Log retention is short in the ephemeral environment.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SUS-01 | No utilization, energy or sustainability KPI is measured | Medium | Open |
| SUS-02 | No retention policy linked to business value exists | Medium | Open |
| SUS-03 | No regional sustainability criterion has been evaluated | Low | Open |
| SUS-04 | Inefficient DynamoDB scans would waste read capacity at scale | Medium | Closed in reference implementation |
| SUS-05 | Repeated full deployments consume build and cloud resources | Low | Mitigated by manual execution |

## Recommended actions

Measure useful work per Lambda invocation and GB-second, define retention by business value and evaluate region using latency, regulation, resilience and sustainability together.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** The design avoids idle capacity and table scans, but no quantitative sustainability target exists.

---

# Cross-pillar priorities

## Production blockers

1. **SEC-01 / SEC-02:** Closed in reference; validate Cognito federation, scopes and CORS in the target environment.
2. **PERF-01 / PERF-02:** Closed in reference; validate indexes and aggregates under representative load.
3. **REL-01 / REL-02 / REL-03:** Define RTO/RPO, enable recovery controls and test restore.
4. **OPS-01 / OPS-02:** Assign ownership and approve SLOs.
5. **COST-01:** Configure account-level financial controls.
6. **SEC-03 / SEC-04 / SEC-05:** Add abuse protection, data governance and supply-chain security.

## Accepted laboratory risks

The following choices are acceptable only because this is a short-lived portfolio laboratory:

- Local Docker mode remains unauthenticated inside the trusted operator network.
- DynamoDB tables are deleted with the ephemeral stack.
- No point-in-time recovery.
- One-day log retention.
- No alarm notification actions.
- Small reserved concurrency.
- No API continuation-token pagination.

## Review cadence

Repeat this review before real users or data, after identity or recovery changes, when a persistent environment is created, after material traffic changes, after an incident or game day, and at least every six months.

## Evidence index

- `backend/app/repository.py`
- `infrastructure/cloudops_infra/stack.py`
- `.github/workflows/validate.yml`
- `.github/workflows/deploy-ephemeral.yml`
- `scripts/check_p0_controls.py`
- `docs/p0-production-controls.md`
- `docs/observability.md`
- `docs/runbook-dlq.md`
- `docs/adr/`

## Reference

This review uses the six pillars of the AWS Well-Architected Framework: operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability.
