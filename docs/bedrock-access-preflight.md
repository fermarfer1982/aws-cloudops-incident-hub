# Bedrock account-access preflight workflow

**Status:** proposed-disabled
**Reviewed sources at:** 2026-07-22T09:06:50Z
**Decision:** **NO-GO PARA INFERENCIA BEDROCK REAL**

This document specifies a future manual, read-only account preflight. The
workflow is checked in but must not be executed by this PR. It neither proves
runtime access nor authorizes inference. The project remains **not
production-ready**.

## Protection and closed inputs

The only trigger is `workflow_dispatch`, from `main`. The job references the
`bedrock-access-preflight` GitHub Environment. An administrator must create that
Environment separately, restrict it to `main`, configure required reviewers and
prevent self-review where supported. Until that protection and its
`AWS_BEDROCK_PREFLIGHT_ROLE_ARN` secret exist, execution must fail or remain
blocked. This PR creates neither the Environment nor the secret.

The workflow grants only `id-token: write` and `contents: read`. Three boolean
confirmations must be true and the Region, model and profile inputs must exactly
equal `eu-west-1`, `amazon.nova-lite-v1:0` and
`eu.amazon.nova-lite-v1:0`. There are no account, ARN, endpoint, prompt or payload
inputs.

## Read-only AWS operations proposed for a later authorization

The future audit role is separate from the inert runtime template. Its reviewed
allowlist is `bedrock:ListFoundationModels`, `bedrock:GetFoundationModel`,
`bedrock:ListInferenceProfiles` and `bedrock:GetInferenceProfile`. No explicit
permission is needed for `sts:GetCallerIdentity`; that call returns sensitive
Account, ARN and UserId fields, so the workflow captures it privately and emits
only boolean indicators. The role must have no `bedrock:InvokeModel`, streaming,
wildcard, IAM, Organizations or infrastructure permissions.

`GetFoundationModelAvailability` exists, but AWS documents the programmatic
model-access flow as applicable to third-party models. It is therefore excluded
from this Nova Lite preflight. Catalog presence, model details and profile
metadata are distinct observations: **ninguna consulta de catálogo o perfil no
demuestra acceso runtime**, capacity, quota, effective IAM or successful
invocation.

## Sanitized evidence

Raw responses are redirected into a runner-temporary directory, never printed,
and removed by a shell trap. The standard-library sanitizer accepts an exact
schema and rejects account IDs, ARNs, access keys, tokens, secrets, signed URLs,
request IDs, UUIDs, email addresses and private IP addresses. Only the fixed
`bedrock-preflight-evidence.json` file is uploaded, for seven days, with
`if-no-files-found: error`. It is never written to `$GITHUB_STEP_SUMMARY`.

## Official sources

| URL | UTC verification | Verified fact | Workflow application | Limitation |
| --- | --- | --- | --- | --- |
| [Bedrock model information](https://docs.aws.amazon.com/bedrock/latest/userguide/models-get-info.html) | 2026-07-22T09:06:50Z | List/GetFoundationModel expose catalog metadata through the Bedrock control plane. | Use both with JSON redirected to temporary files. | Catalog presence does not prove account authorization or invocation. |
| [GetFoundationModelAvailability](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html) | 2026-07-22T09:06:50Z | The API reports authorization, entitlement and Region states. | Deliberately excluded for Amazon Nova Lite. | AWS documents its model-access workflow as applicable to third-party models. |
| [Inference profile information](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-view.html) | 2026-07-22T09:06:50Z | List/GetInferenceProfile are control-plane reads and accept a profile ID. | Confirm the exact system-defined EU profile without retaining returned ARNs. | Profile presence does not prove runtime access. |
| [Supported inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html) | 2026-07-22T09:06:50Z | Geographic profiles have stable destination sets; blocked destinations in SCPs can fail cross-Region inference, and opt-in Regions have special behavior. | Record the documented EU scope and retain SCP review as a separate gate. | The workflow does not inspect Organizations or SCPs. |
| [Geographic cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html) | 2026-07-22T09:06:50Z | Geographic IDs use prefixes such as `eu`; inference requires separate runtime permissions across destinations. | Match only the approved EU ID while granting no runtime action. | No inference is attempted. |
| [STS caller identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html) | 2026-07-22T09:06:50Z | The call requires no explicit permission and returns Account, ARN and UserId. | Validate structure privately and emit booleans only. | It proves the assumed identity exists, not that Bedrock reads or inference succeed. |
| [GitHub OIDC](https://docs.github.com/en/actions/reference/security/oidc) | 2026-07-22T09:06:50Z | OIDC needs `id-token: write`; checkout needs `contents: read`. | Use temporary credentials and no static AWS keys. | OIDC authentication does not prove the role is least privilege. |
| [GitHub Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | 2026-07-22T09:06:50Z | Environment secrets are unavailable until required protection passes. | Require a separately configured protected Environment. | Availability of reviewer protections depends on repository visibility and plan. |
| [Manual workflow inputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs) | 2026-07-22T09:06:50Z | `workflow_dispatch` supports required typed inputs and preserves booleans in `inputs`. | Use an exact closed set of six inputs. | Inputs constrain intent but do not replace Environment approval. |
| [Artifact retention](https://docs.github.com/actions/configuring-and-managing-workflows/persisting-workflow-data-using-artifacts#configuring-a-custom-artifact-retention-period) | 2026-07-22T09:06:50Z | `retention-days` sets per-artifact retention subject to repository limits. | Retain one sanitized JSON artifact for seven days. | Repository policy can impose a lower limit. |

No readiness flag is completed here. IAM remains unapplied, account access
unchecked and unverified, inference untested and unauthorized, ADR-013 remains
Proposed, and the runtime policy remains `DO_NOT_APPLY`.

**NO-GO PARA INFERENCIA BEDROCK REAL**
