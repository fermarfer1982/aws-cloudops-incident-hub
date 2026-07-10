#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github/workflows/deploy-ephemeral.yml"
DESTROY = ROOT / ".github/workflows/destroy-ephemeral.yml"
BOOTSTRAP = ROOT / "bootstrap/github-oidc-role.yml"


def require(content: str, token: str, source: Path, errors: list[str]) -> None:
    if token not in content:
        errors.append(f"{source}: missing required token: {token}")


def forbid(content: str, token: str, source: Path, errors: list[str]) -> None:
    if token.lower() in content.lower():
        errors.append(f"{source}: forbidden token found: {token}")


def main() -> int:
    errors: list[str] = []

    for source in (DEPLOY, DESTROY, BOOTSTRAP):
        if not source.is_file():
            errors.append(f"Missing required file: {source}")

    if errors:
        print("\n".join(errors))
        return 1

    deploy = DEPLOY.read_text(encoding="utf-8")
    destroy = DESTROY.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    for source, content in ((DEPLOY, deploy), (DESTROY, destroy)):
        require(content, "workflow_dispatch:", source, errors)
        require(content, "id-token: write", source, errors)
        require(content, "contents: read", source, errors)
        require(content, "environment: aws-ephemeral", source, errors)
        require(
            content,
            "aws-actions/configure-aws-credentials@v6.1.0",
            source,
            errors,
        )
        require(content, "allowed-account-ids:", source, errors)
        require(content, "github.ref == 'refs/heads/main'", source, errors)
        require(content, "cancel-in-progress: false", source, errors)
        forbid(content, "aws-access-key-id:", source, errors)
        forbid(content, "aws-secret-access-key:", source, errors)
        forbid(content, "pull_request_target", source, errors)

    require(deploy, "if: always() && steps.aws_credentials.outcome == 'success'", DEPLOY, errors)
    require(deploy, "cdk destroy", DEPLOY, errors)
    require(deploy, "DEPLOY-AND-DESTROY", DEPLOY, errors)
    require(destroy, "DESTROY-EPHEMERAL-STACK", DESTROY, errors)

    require(
        bootstrap,
        "token.actions.githubusercontent.com:aud: sts.amazonaws.com",
        BOOTSTRAP,
        errors,
    )
    require(
        bootstrap,
        "repo:${GitHubOwner}/${GitHubRepository}:environment:${GitHubEnvironment}",
        BOOTSTRAP,
        errors,
    )
    require(bootstrap, "Action: sts:AssumeRole", BOOTSTRAP, errors)

    if errors:
        print("OIDC workflow guardrails failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1

    print("OIDC workflow guardrails passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
