---
title: "ADR-0029: Providers consume other providers' Terraform outputs through outputs references"
description: A provider reads another provider's Terraform outputs through outputs.<provider>.<output> references, resolved in memory and ordered producer first.
date: 2026-11-20
audience:
  - contributors
tags:
  - adr
---

# ADR-0029: Providers consume other providers' Terraform outputs through outputs references

## Status
Accepted

## Context
The `tailscale` provider can create an OAuth client (`oauth_client`, #1536) whose id and secret another provider, such as `kubernetes`, needs. Nothing in `core/` read one provider's Terraform outputs. `Orchestrator.build_dependency_graph` only adds edges inside one provider, and apply order came only from `provider_order`. `tailscale` is not in the default order, so it ran after `kubernetes`. The only manual path was copying the secret into the SOPS `secrets.yaml`.

## Decision
A provider may name another provider's Terraform output as `outputs.<provider>.<output>` in `terraform_secrets` (and the fields that fold into it).

- **Syntax:** exactly three dotted parts, each matching `^[a-z][a-z0-9_]*$`. Provider instances (`name@instance`) are excluded. `outputs.` is a reserved prefix and is never looked up in SOPS.
- **Scope:** only the `kubernetes` provider accepts these references, in `terraform_secrets`, `string_data_secrets` and `set_sensitive[*].value_secret`. They are rejected in `data_secrets` (which must be base64), in other providers, and for the provider's own outputs.
- **Resolution:** `TerraformRunner` reads the producer's output with `terraform output -json` in the producer's directory and passes it to the consumer as a `TF_VAR_*` variable through the existing secrets bridge. The value is held in memory only and is never logged or written to the config repo or the generated files. `apply` fails when the output cannot be read, naming the reference and telling the user to apply the producer first. `plan`, `destroy` and `validate` use a placeholder and a warning, because a first apply has no producer state yet.
- **Ordering:** `ProviderBase.get_terraform_output_refs` (additive hook) lets the orchestrator derive provider dependencies, and `ExecutionPlanner.sort_providers` does a stable topological sort, with `provider_order` as the tie-break. Producers run before consumers on apply and after them on destroy. A cycle raises.

## Rationale
It reuses the secrets-to-`TF_VAR_*` bridge and the provider-order machinery, so the change is small and generic: any producer output, including the existing `tailnet_key_<name>` ones, becomes consumable, and no new store of credentials appears.

Alternative rejected: writing the credentials into SOPS `secrets.yaml` on first create. It makes an apply mutate the config repo, adds a write path to the encryption keys, and the copy drifts after rotation.

The consumer's Terraform state holds the value, as with any Terraform-managed secret.

## Related Issues
- Issue #1536: tailscale `oauth_client` resource whose credentials other providers can consume

## Related Documentation
- [Tailscale provider](../providers/tailscale.md)
- [Kubernetes provider](../providers/kubernetes.md)
- [Dependency ordering](../configuration/dependency-ordering.md)
