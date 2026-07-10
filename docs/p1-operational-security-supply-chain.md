# P1 operational security and supply-chain controls

## Scope

This phase adds preventive controls to the AWS edge and to the GitHub software-delivery path. It does not claim that the workload is production-ready and it does not deploy AWS resources.

## API abuse protection

The HTTP API default stage has explicit throttling limits:

| Setting | Default | CDK context |
|---|---:|---|
| Steady request rate | 10 requests/second | `api_throttling_rate_limit` |
| Burst capacity | 20 requests | `api_throttling_burst_limit` |

Example synthesis with alternative limits:

```bash
cd infrastructure
cdk synth \
  -c api_throttling_rate_limit=25 \
  -c api_throttling_burst_limit=50
```

These are defensive defaults for a portfolio workload, not capacity values derived from production traffic. They must be validated with representative load tests before a persistent deployment. Throttling complements Cognito and JWT scopes; it does not replace authorization, tenant isolation or application-level quotas.

## Dependency maintenance

`.github/dependabot.yml` checks weekly for updates to:

- Backend Python dependencies.
- Infrastructure Python and AWS CDK dependencies.
- The backend container base image.
- GitHub Actions.

Minor and patch updates are grouped where appropriate to reduce pull-request noise. Major upgrades remain separate so they receive explicit review.

## Static security analysis

`.github/workflows/codeql.yml` runs CodeQL for Python on:

- Pull requests targeting `main`.
- Pushes to `main`.
- A weekly schedule.
- Manual invocation.

The workflow uses read-only repository permissions plus `security-events: write`, which is required to publish code-scanning results. Findings must be triaged in the repository Security view; a green workflow does not guarantee absence of vulnerabilities.

## Secret protection

Public GitHub repositories receive provider-pattern secret scanning automatically. Repository push protection and any additional non-provider or custom patterns are settings that must be confirmed in the GitHub Security configuration; they cannot be proven only by committing workflow files.

Defense in depth is provided by `scripts/check_repository_secrets.py`, which fails CI when it detects common high-confidence patterns such as AWS access-key identifiers, private-key headers and GitHub personal access tokens. This lightweight check is intentionally not described as a replacement for GitHub secret scanning.

A real secret found in Git history must be revoked or rotated immediately. Removing it from Git history without revoking it is insufficient.

## SBOM

`.github/workflows/sbom.yml` generates an SPDX JSON software bill of materials using the verified Anchore SBOM action and stores it as a workflow artifact for 30 days.

The workflow runs after pushes to `main`, monthly and on demand. The artifact is an inventory of the repository at the scanned revision. A production release process should additionally generate an SBOM from the exact deployable artifact or container image and bind it to release provenance.

## Vulnerability reporting

`SECURITY.md` defines private reporting expectations and a secret-exposure response. Exploitable details must not be published in normal issues, pull requests or discussions.

## Manual GitHub controls checklist

The following controls require repository settings or observation in GitHub and therefore remain evidence items:

- Confirm CodeQL produces results under **Security → Code scanning**.
- Confirm Dependabot alerts and security updates are enabled.
- Confirm secret scanning is active.
- Enable push protection where available.
- Confirm private vulnerability reporting is enabled where available.
- Protect `main` with required validation and CodeQL checks.
- Review and remediate open security alerts with an assigned owner and due date.

## Validation

```bash
python3 scripts/check_repository_secrets.py
python3 scripts/check_security_supply_chain.py

cd infrastructure
PYTHONPATH=. python3 -m pytest -q tests
cdk synth --quiet
```

## Residual risks

- Throttling values have not been validated with representative load.
- No per-user or per-tenant application quota exists.
- WAF or an edge protection layer has not been selected because the threat model and traffic profile are not yet approved.
- GitHub repository settings still require manual evidence.
- The SBOM is not yet attached to a signed production release.
- There is no real security incident exercise or dependency-compromise game day.
