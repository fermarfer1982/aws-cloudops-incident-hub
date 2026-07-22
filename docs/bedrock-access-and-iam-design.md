# Bedrock account access and least-privilege IAM design

**Status:** proposed-disabled

**Decision:** **NO-GO PARA INFERENCIA BEDROCK REAL**

**Scope:** documentary design only; no account check, IAM application or inference

**Reviewed sources at:** 2026-07-22T06:10:17Z

This design preserves Amazon Nova Lite (`amazon.nova-lite-v1:0`), the EU
system-defined inference profile (`eu.amazon.nova-lite-v1:0`), `eu-west-1` as
source, `bedrock-runtime`, non-streaming `Converse`, and an EU scope. It does not
establish that the account can use the model. ADR-013 remains **Proposed** and the
project remains **not production-ready**.

## What official AWS documentation establishes

| Official source | Verified fact and interpretation | Remaining uncertainty |
| --- | --- | --- |
| [Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html) | `Converse` requires exactly `bedrock:InvokeModel`; streaming is a separate operation and permission. The future runtime therefore does not need `InvokeModelWithResponseStream`. | A documented permission is not proof that the future identity has it or that an invocation succeeds. |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html) | `InvokeModel` supports inference-profile and foundation-model resources. The current condition key is `bedrock:InferenceProfileArn`; its ARN forms include account-bearing inference profiles and accountless foundation models. | Effective IAM, boundaries and organization controls have not been inspected. |
| [Nova Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html) | Nova Lite supports `Converse`. For source `eu-west-1`, the EU profile snapshot routes to exactly `eu-central-1`, `eu-north-1`, `eu-west-1`, and `eu-west-3`. | AWS documentation can change; revalidation is mandatory immediately before rendering IAM or authorizing execution. |
| [Inference-profile prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html) | An inference-profile grant must also cover its foundation model in every destination. A prose line historically names `aws:InferenceProfileArn`, while its examples use `bedrock:InferenceProfileArn`. | The discrepancy is resolved in favor of the current Service Authorization Reference, the authoritative action/condition catalog. |
| [Cross-Region profile support](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html) | Blocking any destination with an SCP can fail the whole request. Cross-Region routing can reach an opt-in Region even when that Region was not manually enabled for the account. | Account SCPs, Region restrictions and source-Region enablement remain unchecked. |
| [Model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) and [product IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access-product-ids.html) | General access can be enabled by default when permissions are correct. Amazon models are not AWS Marketplace products and have no product ID; third-party Marketplace agreement and entitlement flows are different. | Neither a default nor absence of a Marketplace product ID confirms access for this account. Terms still require human review. |
| [Get/List foundation model information](https://docs.aws.amazon.com/bedrock/latest/userguide/models-get-info.html) | `GetFoundationModel` and `ListFoundationModels` are read-only catalog discovery methods. | Catalog presence and regional metadata do not prove IAM authorization, account access, capacity, quota or successful invocation. |
| [GetFoundationModelAvailability](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html) | The API reports agreement, authorization, entitlement and Region availability states. | The documented programmatic model-access workflow applies to third-party models; it must not be treated as sufficient evidence for Amazon Nova Lite. |

No `aws:RequestedRegion` condition is proposed. The exact resource set already
fixes the source profile and four destinations, while an extra request-region
condition is not necessary for the approved minimum and must not accidentally
constrain service-side cross-Region routing.

## Inert runtime policy template

[`policies/bedrock-nova-lite-eu-invoke.template.json`](../policies/bedrock-nova-lite-eu-invoke.template.json)
is an envelope, not an attachable IAM policy. `metadata` marks it `DO_NOT_APPLY`
and `disabled`; `${AWS_PARTITION}`, `${SOURCE_REGION}` and `${AWS_ACCOUNT_ID}`
must be resolved only in a separately reviewed future change. It contains no
principal, role name, real account identifier or account ARN.

The nested runtime policy grants only `bedrock:InvokeModel` to:

- the exact EU system-defined inference profile in the future account and source Region;
- `amazon.nova-lite-v1:0` in exactly `eu-central-1`, `eu-north-1`, `eu-west-1`, and `eu-west-3`;
- foundation-model access only when `bedrock:InferenceProfileArn` equals the approved profile ARN.

It grants no streaming, control-plane, Marketplace, IAM, STS, Organizations,
CloudFormation, Lambda, S3 or logging actions. It has no wildcard, regional
fallback, alternative model, automatic retry, global profile or application
inference profile.

## Runtime identity versus audit identity

The future application runtime receives only the nested policy above. It must
not receive `AmazonBedrockFullAccess` or catalog/access-management permissions.

A distinct future audit identity may be reviewed for read-only operations such
as `GetFoundationModel`, `ListFoundationModels`, `GetInferenceProfile`, or an
applicable availability query. This PR grants none of them. Audit results must
record whether they describe catalog, regional availability, account state or
IAM; these are not interchangeable and none alone proves effective invocation.

## Mandatory future sequence (not executed)

1. Recheck the official model card from `eu-west-1` and record all destinations.
2. Have an authorized administrator confirm no SCP or Region restriction blocks any destination.
3. Confirm the source Region is enabled for the account.
4. Query catalog and regional model metadata with a separately authorized read-only identity.
5. Check effective account access using the applicable official mechanism and record its limits.
6. Review the current Amazon Nova terms with an accountable human owner.
7. Render the inert template with a non-secret account identifier, then review its exact diff and policy simulation where available.
8. Confirm the intended runtime identity, permission boundaries and absence of broader grants.
9. Apply IAM only in a separate approved PR.
10. Run a non-inference account/readiness check when an applicable official check exists.
11. Obtain explicit human authorization for one synthetic request, its cost ceiling and automatic cleanup.
12. In a later workflow/PR, perform at most one synthetic inference and retain sanitized evidence.

`ListFoundationModels` or `GetFoundationModel` can establish catalog metadata.
Regional documentation or `GetInferenceProfile` can establish a destination
snapshot. IAM review can establish a policy grant. Model-access state can
describe account authorization. Only a tightly controlled invocation can prove
that invocation actually works at that moment; it remains prohibited here.

## Exact execution gates

All of these must be true in a future, separately reviewed record before any
request: destinations revalidated; SCP compatibility checked; source Region
enabled; catalog availability checked; account access checked and verified;
terms reviewed; rendered IAM reviewed and applied; runtime identity verified;
non-inference check completed where applicable; explicit human execution
approval granted. Until then the checked-in readiness record keeps every
execution or access boolean false and requires review.

This PR performs no AWS operation and changes no IAM, SCP, role, infrastructure,
backend, workflow, environment, variable, secret, dependency or ADR.
**NO-GO PARA INFERENCIA BEDROCK REAL**.
