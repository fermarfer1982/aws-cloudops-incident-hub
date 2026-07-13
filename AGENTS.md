# AWS CloudOps Incident Hub

## Repository

- Repository: fermarfer1982/aws-cloudops-incident-hub
- Source of truth: GitHub
- Default branch: main
- Execution environment: mirofish
- Local path: /opt/aws-cloudops-incident-hub

## Project status

- WA-014 completed and evidenced.
- CloudWatch -> SNS -> Amazon Q Developer -> Slack validated.
- Ephemeral AWS deployments use GitHub Actions and OIDC.
- The project is a validated laboratory reference architecture.
- Do not describe it as production-ready.

## Working rules

- Inspect the current branch and working tree before changing files.
- Treat GitHub as the source of truth for repository history and review state.
- Use mirofish as the execution environment, but never deploy directly to AWS from mirofish.
- Start every change from an updated main branch.
- Create one branch per task.
- Do not commit directly to main.
- Run local validation before committing.
- Create a pull request for every change.
- Do not merge while checks are pending or failing.
- Never commit credentials, API keys, AWS account IDs, Slack workspace or channel IDs, private IP addresses, passwords, tokens, secrets or sensitive internal data.
- Do not use persistent AWS access keys.
- AWS deployments must run through GitHub Actions with OIDC and temporary credentials.
- Ephemeral stacks must always be destroyed and verified.
- Preserve least-privilege IAM.
- Do not invent test results or runtime evidence.
- Avoid long heredocs in interactive SSH sessions.
- Do not modify files unless the requested task requires it.

## Immediate priorities

1. Prepare v1.0.0-lab.
2. Review the moderate Dependabot vulnerability.
3. Improve the public README.
4. Execute WA-019 game day.
5. Prepare WA-020 release and rollback runbook.
6. Publish a verifiable SBOM.
7. Estimate cost per 1,000 incidents.
