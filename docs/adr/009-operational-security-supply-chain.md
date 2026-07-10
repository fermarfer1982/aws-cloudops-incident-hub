# ADR-009: Operational security and supply-chain controls

- Status: Accepted
- Date: 2026-07-10

## Context

The reference architecture already enforces authentication, authorization scopes and an explicit CORS allowlist, but it still lacked explicit API throttling and automated software-supply-chain controls. The Well-Architected backlog identified abuse protection, dependency analysis, secret detection and SBOM generation as open risks.

## Decision

1. Configure default-stage throttling on API Gateway HTTP API with conservative, configurable defaults.
2. Use Dependabot for scheduled updates across Python, the backend container and GitHub Actions.
3. Run GitHub CodeQL advanced setup for Python on pull requests, main-branch pushes and a weekly schedule.
4. Rely on GitHub secret scanning as the primary platform control for the public repository, supplemented by a narrow CI pattern guardrail.
5. Generate a repository SPDX JSON SBOM with a verified partner action and retain it as a workflow artifact for 30 days.
6. Add a security policy and a CI guardrail that prevents accidental removal or unsafe reconfiguration of these controls.

## Consequences

### Positive

- The API has a defined first line of defense against accidental or abusive request bursts.
- Dependency and CodeQL findings are surfaced continuously.
- Common credential leaks can block the normal validation workflow.
- The repository produces a machine-readable component inventory.
- Controls are versioned and reviewable as code.

### Trade-offs

- Throttling defaults are assumptions until load testing establishes a traffic baseline.
- CodeQL and SBOM jobs consume GitHub Actions minutes.
- Dependabot can create maintenance noise and still requires human review.
- Regex-based secret checks can produce false positives and cannot detect every secret type.
- The repository SBOM is not equivalent to an SBOM of the final runtime artifact.

## Rejected alternatives

- Storing permanent scanner credentials: rejected because GitHub-native and verified actions can run without long-lived external secrets.
- Treating a custom regex script as full secret scanning: rejected because provider validation and full-history scanning belong to the platform control.
- Adding WAF without an approved threat model: rejected for this phase because the correct edge architecture and rule set depend on deployment and traffic requirements.
- Disabling dependency update automation to avoid pull-request noise: rejected because grouped weekly updates provide a manageable maintenance cadence.

## Follow-up evidence

- CodeQL results visible in the Security tab.
- Dependabot alerts and security updates enabled.
- Secret scanning and push protection status recorded.
- Successful SBOM artifact downloaded and inspected.
- Load test evidence supporting API throttling values.
- Branch protection requiring validation and security checks.
