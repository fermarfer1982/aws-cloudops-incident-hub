# AWS Well-Architected Review

## Review metadata

- **Workload:** AWS CloudOps Incident Hub
- **Review type:** Repository-based self-assessment
- **Review date:** 2026-07-10
- **Reviewer:** Fernando Martínez Fernández
- **Framework:** AWS Well-Architected Framework, six pillars
- **Environment assessed:** Local zero-cost laboratory plus the proposed ephemeral AWS architecture
- **Production readiness:** Not production-ready

> This document is a technical self-assessment, not an AWS Well-Architected Tool review and not an external audit. Findings are based on the code, infrastructure definitions, workflows, tests, runbooks, and architectural decisions stored in this repository.

## Scope and assumptions

The reviewed workload accepts infrastructure incidents, classifies them, and persists them. The AWS design uses API Gateway, Lambda, EventBridge, SQS, a Dead Letter Queue, DynamoDB, CloudWatch, and GitHub Actions with OIDC for temporary deployments.

The local implementation uses Docker, FastAPI, and DynamoDB Local. The public GitHub Pages dashboard uses demonstration data and does not expose the local network.

The following assumptions constrain the conclusions:

- The workload is currently a portfolio laboratory, not a business-critical production service.
- The AWS stack is designed to be deployed temporarily and destroyed after validation.
- No persistent production traffic profile, RTO, RPO, SLO, compliance regime, or data classification has been approved.
- A real AWS deployment may incur charges. The repository does not claim a mathematical guarantee of zero AWS cost.
- Findings marked **Accepted for laboratory** must be remediated before a production launch.

## Rating model

| Rating | Meaning |
|---|---|
| Low risk | Controls are appropriate for the current scope; minor improvements remain. |
| Medium risk | Important controls exist, but one or more material gaps remain. |
| High risk | A production launch would expose an unacceptable failure, security, or governance risk. |
| Not assessed | Evidence or requirements are insufficient to make a defensible conclusion. |

## Executive summary

| Pillar | Current rating | Main strength | Main risk |
|---|---|---|---|
| Operational excellence | Medium | Infrastructure as Code, CI, runbooks, ephemeral deployment evidence | No approved SLO, ownership model, or alert-routing process |
| Security | High for production | OIDC federation, temporary credentials, encryption, constrained workflows | Public unauthenticated API with permissive CORS |
| Reliability | Medium | EventBridge, SQS, DLQ, retries, idempotency, alarms | No approved RTO/RPO, restore test, or regional recovery strategy |
| Performance efficiency | Medium | Serverless architecture, ARM64 Lambda, batching, bounded concurrency | DynamoDB scans and synchronous metrics aggregation do not scale |
| Cost optimization | Low for laboratory / Medium for production | Ephemeral lifecycle, cost guardrails, on-demand services | No AWS Budget, anomaly detection, or measured unit economics |
| Sustainability | Low for laboratory / Medium for production | Ephemeral resources, managed services, ARM64 compute | No workload utilization baseline or sustainability KPI |

### Overall conclusion

The project is strong as a demonstrable serverless laboratory. It shows disciplined automation, asynchronous processing, idempotency, observability, short-lived credentials, and cleanup controls. It is deliberately **not production-ready**. The highest-priority production blockers are authentication and authorization, scalable DynamoDB access patterns, explicit recovery objectives, tested backup/restore procedures, and operational ownership.

---

# 1. Operational excellence

## Evidence

- AWS CDK defines the cloud architecture.
- GitHub Actions performs linting, application tests, infrastructure tests, CDK synthesis, cost checks, and OIDC workflow checks.
- Manual deployment requires explicit confirmation and uses an isolated GitHub environment.
- Deployment evidence is retained temporarily as a workflow artifact.
- Automatic destruction and an independent emergency cleanup workflow exist.
- CloudWatch dashboards, alarms, and a DLQ runbook are documented.
- Architectural decisions are recorded as ADRs.

## Strengths

1. Changes are versioned and evaluated before merge.
2. Infrastructure changes are reproducible through CDK.
3. The deployment workflow validates identity, runs smoke tests, and verifies stack removal.
4. Failure handling is documented for the DLQ.
5. The repository separates normal CI from explicit cloud deployment.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| OPS-01 | No approved service owner, escalation path, or on-call responsibility | High | Open |
| OPS-02 | No SLO, error budget, availability target, or latency objective | High | Open |
| OPS-03 | CloudWatch alarms have no notification or incident-management destination | Medium | Accepted for laboratory |
| OPS-04 | No game-day or failure-injection evidence | Medium | Open |
| OPS-05 | No automated release notes, change calendar, or rollback decision procedure | Medium | Open |

## Recommended actions

- Define workload owner, technical owner, security owner, and cost owner.
- Approve measurable SLOs before production deployment.
- Route alarms to an approved incident channel using SNS, Chatbot, PagerDuty, or equivalent.
- Add a game-day scenario for Lambda failure, queue backlog, and DLQ redrive.
- Add a release and rollback runbook linked from the deployment workflow.

## Pillar rating

**Medium risk.** The engineering workflow is mature for a portfolio project, but operational ownership and measurable outcomes are missing.

---

# 2. Security

## Evidence

- GitHub Actions uses OIDC and STS temporary credentials.
- No long-lived AWS access keys are required in GitHub.
- The IAM trust policy is restricted to the repository and GitHub environment.
- DynamoDB and SQS use AWS-managed encryption.
- Lambda permissions are granted to required project resources.
- OIDC workflow guardrails reject unsafe triggers and permanent credential patterns.
- The deployment verifies the expected AWS account.

## Strengths

1. Workload deployment uses federation rather than stored cloud credentials.
2. The trust relationship is narrower than a repository-wide wildcard.
3. Encryption at rest is enabled for the principal data and queue services.
4. Session duration and execution context are bounded.
5. The public dashboard contains only demonstration data.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SEC-01 | API Gateway endpoint has no authentication or authorization | Critical | Accepted for laboratory only |
| SEC-02 | CORS allows every origin | High | Accepted for laboratory only |
| SEC-03 | No AWS WAF, throttling policy, request quota, or abuse protection is defined | High | Open |
| SEC-04 | No formal data classification, retention policy, or privacy assessment | High | Open |
| SEC-05 | No dependency vulnerability scanning, secret scanning policy, or SBOM generation | Medium | Open |
| SEC-06 | IAM permissions rely partly on CDK bootstrap roles whose effective permissions require separate review | Medium | Open |
| SEC-07 | No CloudTrail, GuardDuty, Security Hub, or centralized security account design | Medium | Deferred to multi-account architecture |

## Recommended actions

- Require authentication using Amazon Cognito, IAM authorization, or an enterprise identity provider.
- Implement authorization scopes for incident creation, reading, status changes, and administration.
- Replace wildcard CORS with an explicit allowlist.
- Add API Gateway throttling and request quotas; evaluate AWS WAF for public exposure.
- Document data classification, retention, deletion, and audit requirements.
- Add Dependabot or equivalent dependency review, code scanning, secret scanning, and SBOM generation.
- Review the deployed CloudFormation and bootstrap-role policies before any production deployment.

## Pillar rating

**High risk for production.** OIDC and temporary credentials are strong controls, but an unauthenticated public API is an explicit production blocker.

---

# 3. Reliability

## Evidence

- EventBridge decouples ingestion from processing.
- SQS provides durable buffering and retries.
- A DLQ retains messages that exceed the retry limit.
- Lambda reports partial batch failures.
- Deterministic event identifiers and conditional writes provide idempotency.
- Queue-age, Lambda-error, and DLQ alarms are defined.
- An emergency cleanup workflow handles incomplete ephemeral deployments.

## Strengths

1. The ingestion path does not depend on immediate downstream availability.
2. Failed SQS records can be retried independently.
3. Duplicate delivery is expected and handled.
4. Backlog age and DLQ depth are observable.
5. Managed regional services reduce infrastructure maintenance.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| REL-01 | RTO and RPO are undefined | High | Open |
| REL-02 | DynamoDB point-in-time recovery and backup policy are not enabled | High | Accepted for ephemeral laboratory only |
| REL-03 | Restore procedures have not been tested | High | Open |
| REL-04 | Architecture is single-region with no documented regional recovery strategy | Medium | Open |
| REL-05 | API Gateway availability and client retry behavior are not documented | Medium | Open |
| REL-06 | EventBridge target delivery failure handling beyond the SQS target is not explicitly tested | Medium | Open |
| REL-07 | Alarm notifications are not routed to responders | Medium | Accepted for laboratory |

## Recommended actions

- Define RTO and RPO from business requirements.
- Enable DynamoDB point-in-time recovery for persistent environments.
- Create and test restore and regional recovery runbooks.
- Define client timeout, retry, backoff, and idempotency behavior.
- Add integration tests for poison messages, EventBridge delivery failure, queue saturation, and redrive.
- Decide whether single-region recovery is sufficient or a multi-region pattern is required.

## Pillar rating

**Medium risk.** The event-driven design has strong failure isolation, but data recovery and business recovery objectives are not defined.

---

# 4. Performance efficiency

## Evidence

- Lambda uses ARM64 and 256 MB memory.
- Reserved concurrency bounds workload consumption.
- SQS processing uses batches and a batching window.
- DynamoDB uses on-demand billing.
- API and processor duration p95 are displayed in CloudWatch.
- The architecture uses managed serverless services.

## Strengths

1. Compute scales independently across ingestion and processing.
2. Queue buffering absorbs short traffic bursts.
3. Batch processing reduces invocation overhead.
4. ARM64 can improve price-performance for compatible workloads.
5. Duration and throttling metrics are available for tuning.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| PERF-01 | `GET /events` uses DynamoDB Scan and in-memory filtering | High at scale | Accepted for laboratory only |
| PERF-02 | Metrics are calculated by scanning and aggregating incident records synchronously | High at scale | Accepted for laboratory only |
| PERF-03 | No load test, throughput objective, or representative traffic model exists | High | Open |
| PERF-04 | Reserved concurrency of two may throttle legitimate bursts | Medium | Intentional cost guardrail |
| PERF-05 | Lambda memory, timeout, batch size, and batching window have not been tuned with measurements | Medium | Open |
| PERF-06 | No pagination contract or continuation token is exposed by the API | Medium | Open |

## Recommended actions

- Design DynamoDB access patterns before production implementation.
- Add GSIs for site, severity, status, and time-based queries only where justified by access patterns.
- Replace full-table metric scans with incremental counters, DynamoDB Streams aggregation, or scheduled materialization.
- Implement API pagination with opaque continuation tokens.
- Add load tests and measure latency, throttling, concurrency, queue age, and cost per incident.
- Tune Lambda memory and SQS batch settings from empirical results.

## Pillar rating

**Medium risk.** The service selection is efficient, but the current data-access design is intentionally limited to small laboratory datasets.

---

# 5. Cost optimization

## Evidence

- The default operating mode is local and does not require AWS resources.
- AWS deployment is manual, temporary, and followed by automatic destruction.
- A separate emergency destroy workflow exists.
- Static guardrails reject NAT Gateway, EC2, RDS, ALB, EKS, OpenSearch, and ElastiCache resources.
- DynamoDB uses on-demand capacity.
- Lambda concurrency, memory, and timeouts are bounded.
- CloudWatch uses native service metrics rather than custom metrics.
- Log retention is one day for ephemeral demonstrations.

## Strengths

1. The project avoids idle infrastructure in its default state.
2. Expensive resource categories are automatically rejected.
3. Serverless consumption follows workload activity.
4. Cleanup is part of the deployment lifecycle rather than a manual afterthought.
5. The README explicitly avoids promising mathematically guaranteed zero AWS charges.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| COST-01 | No AWS Budget, cost anomaly monitor, or billing alarm is defined | High before real deployment | Open |
| COST-02 | No cost allocation tags beyond basic project/environment tags | Medium | Open |
| COST-03 | No cost-per-incident model or traffic-based estimate | Medium | Open |
| COST-04 | CDK bootstrap resources may remain after stack destruction | Medium | Documented |
| COST-05 | CloudWatch dashboard and alarms can incur charges in a real account | Medium | Documented |
| COST-06 | Emergency cleanup still depends on the federated role and GitHub availability | Medium | Accepted risk |

## Recommended actions

- Configure an AWS Budget and cost anomaly detection before the first real deployment.
- Define mandatory tags for owner, environment, application, cost center, and expiration.
- Estimate cost per 1,000 incidents for low, expected, and peak traffic.
- Document and periodically inspect CDK bootstrap resources.
- Add a scheduled orphan-resource inventory outside this repository if deployments become routine.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** Lifecycle controls are strong, but account-level financial controls are not implemented.

---

# 6. Sustainability

## Evidence

- The workload is not kept running in AWS by default.
- Managed serverless services scale with demand.
- Lambda uses ARM64.
- SQS batching reduces per-message invocation overhead.
- Log retention is deliberately short in ephemeral environments.
- Local development reuses an existing Ubuntu server.

## Strengths

1. Idle cloud capacity is avoided by design.
2. Managed services reduce overprovisioning.
3. ARM64 compute is selected for the Lambda functions.
4. Batching reduces invocation frequency.
5. Data and log retention are constrained for the demonstration environment.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SUS-01 | No utilization, energy, or sustainability KPI is measured | Medium | Open |
| SUS-02 | No data-retention policy linked to business value exists | Medium | Open |
| SUS-03 | No regional sustainability criterion has been evaluated | Low | Open |
| SUS-04 | Inefficient DynamoDB scans would waste read capacity at scale | Medium | Accepted for laboratory only |
| SUS-05 | Repeated full deployments may consume unnecessary build and cloud resources | Low | Mitigated by manual execution |

## Recommended actions

- Track incidents processed per Lambda invocation and per GB-second.
- Remove scan-based access patterns before scale.
- Define data and log retention according to business and compliance value.
- Evaluate deployment region using latency, regulatory, resilience, and sustainability requirements together.
- Prefer targeted deployments and cached build dependencies where safe.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** The ephemeral serverless model is favorable, but no quantitative sustainability target exists.

---

# Cross-pillar priorities

## Production blockers

1. **SEC-01:** Add authentication and authorization.
2. **SEC-02:** Restrict CORS.
3. **PERF-01 / PERF-02:** Replace DynamoDB scans with production access patterns.
4. **REL-01 / REL-02 / REL-03:** Define RTO/RPO, enable recovery controls, and test restore.
5. **OPS-01 / OPS-02:** Assign ownership and approve SLOs.
6. **COST-01:** Configure account-level cost controls before deployment.

## Accepted laboratory risks

The following choices are acceptable only because the project is a short-lived portfolio laboratory:

- Public unauthenticated API during a controlled ephemeral test.
- Wildcard CORS.
- DynamoDB table removal on stack destruction.
- No point-in-time recovery.
- One-day log retention.
- No alarm notification actions.
- Small reserved concurrency.
- Scan-based list and metric operations.

## Review cadence

Repeat this review when any of the following occurs:

- The workload is proposed for real users or business data.
- Authentication or multi-account architecture is introduced.
- A persistent AWS environment is created.
- Traffic assumptions change materially.
- Recovery objectives are approved.
- A major AWS service or architecture component changes.
- Six months have elapsed since the previous review.

## Evidence index

- `infrastructure/cloudops_infra/stack.py`
- `.github/workflows/validate.yml`
- `.github/workflows/deploy-ephemeral.yml`
- `.github/workflows/destroy-ephemeral.yml`
- `scripts/check_zero_cost.py`
- `scripts/check_oidc_workflows.py`
- `docs/observability.md`
- `docs/runbook-dlq.md`
- `docs/github-oidc-deployment.md`
- `docs/adr/`

## Reference

This review uses the six pillars of the AWS Well-Architected Framework: operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability.