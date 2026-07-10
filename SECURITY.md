# Security policy

## Supported versions

The default branch is the only supported version of this portfolio project. Historical tags and demonstration branches are not maintained as security-supported releases.

## Reporting a vulnerability

Do not disclose exploitable details in a public issue, pull request, discussion or commit message.

Use GitHub's private vulnerability reporting flow from the repository **Security** tab when it is available. Include:

- A concise impact statement.
- The affected path, component or workflow.
- Reproduction steps that do not expose real credentials or personal data.
- Suggested remediation, when known.

If private reporting is unavailable, contact the repository owner through the GitHub profile without publishing exploit details. A minimal public issue may be used only to request a private communication channel.

## Secret exposure response

A detected credential must be treated as compromised:

1. Revoke or rotate it immediately at the issuing service.
2. Remove it from current files and CI configuration.
3. Review audit logs for unauthorized use.
4. Remove it from Git history only after rotation; history rewriting is not a substitute for revocation.
5. Record the incident and prevention action without reproducing the secret.

## Scope

The static GitHub Pages demonstration contains simulated data. The Docker laboratory must not store production credentials or regulated data. AWS deployment workflows use OIDC and temporary STS credentials rather than long-lived AWS access keys.
