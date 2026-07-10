# ADR-006: Multi-account production landing zone

- **Status:** Accepted as target-state architecture
- **Date:** 2026-07-10

## Context

AWS CloudOps Incident Hub began as a local zero-cost laboratory with an AWS serverless design represented in CDK. The repository now includes asynchronous processing, observability, GitHub OIDC, ephemeral deployment controls, and a Well-Architected self-assessment.

A single AWS account is sufficient for a temporary demonstration but does not provide the isolation required for production operation. In particular, it cannot create independent boundaries for:

- Production and non-production data.
- Workload deployment and organization governance.
- Security administration and workload administration.
- Mutable workload resources and retained audit evidence.
- Environment-level budgets, quotas, and blast radius.
- Human access and automated deployment permissions.

AWS guidance recommends managing accounts in one organization, using multiple foundational accounts for functions such as security and logging, and separating production from development and test workloads.

## Decision

The production target state will use one AWS Organization with workload-oriented OUs and separate accounts for:

- Management.
- Log Archive.
- Security Tooling / Audit.
- Shared Services.
- Network capabilities when justified.
- CloudOps Dev.
- CloudOps Stage.
- CloudOps Prod.
- Sandbox.

The landing zone should use AWS Control Tower when creating a new environment unless an existing enterprise landing zone provides equivalent governed capabilities.

Human access will use an organization instance of AWS IAM Identity Center. Group-based permission sets will be used instead of shared users or persistent workforce access keys.

Application delivery will use GitHub OIDC and a dedicated deployment role in each workload account. Artifacts will be built once and promoted through Dev, Stage, and Prod. Production promotion will require protected-environment approval and separation of duties.

Central audit data will be owned by Log Archive. Supported security services will use delegated administration in Security Tooling. The management account will not host application workloads.

SCPs will be introduced progressively through a policy-staging OU. They will define maximum permissions but will not be treated as identity policies or as permission grants.

## Account and OU model

```text
Root
├── Security
│   ├── Log Archive
│   └── Security Tooling
├── Infrastructure
│   ├── Shared Services
│   └── Network
├── Workloads-NonProduction
│   ├── CloudOps Dev
│   └── CloudOps Stage
├── Workloads-Production
│   └── CloudOps Prod
├── Sandbox
│   └── Sandbox Users
└── Suspended
```

## Consequences

### Positive

- Production compromise has a smaller blast radius.
- Developers do not require production write access.
- Workload administrators cannot control central audit evidence.
- Security services can aggregate findings across accounts.
- Costs, quotas, ownership, and data boundaries are environment specific.
- CI/CD permissions can be constrained to target accounts.
- Governance controls can differ between Sandbox, non-production, and production.
- Account suspension and closure become explicit lifecycle states.

### Negative

- Additional accounts and organization services create cost and operational overhead.
- Account vending, identity assignments, delegated administration, and SCPs require specialist ownership.
- Cross-account pipelines and central logging introduce more policies to test.
- Control Tower-managed resources must be changed only through supported mechanisms.
- Some organization-level mistakes can affect many accounts.
- The design requires real business decisions for SLO, RTO, RPO, retention, compliance, and regional recovery.

## Alternatives considered

### Keep one AWS account with environment prefixes

Rejected for production. Naming conventions do not provide the same security, billing, quota, and blast-radius boundaries as separate accounts.

### Use one account per application but combine Dev, Stage, and Prod

Rejected. Production and non-production operators, data, budgets, and deployment paths require separate boundaries.

### Create a dedicated account for every microservice

Not selected for this workload. The application is currently a cohesive serverless workload, and excessive account fragmentation would add governance burden without a demonstrated isolation requirement.

### Put shared CI/CD and application workloads in the management account

Rejected. The management account has organization-wide significance and should not host workload resources.

### Require centralized VPC networking immediately

Rejected. The core serverless path does not require a VPC. Central networking will be introduced only for a justified hybrid, private access, DNS, or inspection requirement.

### Build a landing zone manually without Control Tower

Possible, but not preferred for a new environment. It transfers responsibility for guardrails, account lifecycle, logging, and drift management to the platform team. It remains an option when an existing enterprise landing zone or regulatory requirement makes Control Tower unsuitable.

## Production constraints

This ADR does not authorize a production launch. Production remains blocked until:

- Authentication, authorization, and restricted CORS are implemented.
- DynamoDB Scan is removed from production access paths.
- SLO, RTO, RPO, ownership, and incident routing are approved.
- Restore and rollback are tested.
- AWS Budgets and anomaly detection are enabled.
- Central logging and delegated security services are operational.
- Production deployment roles and permission sets pass security review.

## Validation

The repository maintains:

- `governance/organization-blueprint.json`.
- `docs/multi-account-production-architecture.md`.
- `docs/multi-account-control-matrix.md`.
- `docs/multi-account-migration-plan.md`.
- `scripts/check_multi_account_blueprint.py`.

The CI guardrail validates the presence and internal consistency of these artifacts. It does not prove that an AWS landing zone has been deployed or configured correctly.

## Review triggers

Review this decision when:

- The target organization already has a landing zone.
- Control Tower adoption is approved or rejected.
- A production Region or data-residency requirement changes.
- Hybrid connectivity is introduced.
- A second production workload shares the organization.
- The workload requires multi-region active operation.
- Organization-level security or compliance requirements change.
