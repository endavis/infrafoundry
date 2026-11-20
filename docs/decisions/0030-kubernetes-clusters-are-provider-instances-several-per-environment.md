---
title: "ADR-0030: Kubernetes clusters are provider instances, several per environment"
description: Each extra Kubernetes cluster is a provider instance kubernetes@name, selected by a cluster key, and the primary keeps the plain kubernetes id
date: 2026-11-20
audience:
  - contributors
tags:
  - adr
---

# ADR-0030: Kubernetes clusters are provider instances, several per environment

## Status
Accepted

## Context
An environment could address one Kubernetes cluster: `provider_settings.kubernetes` held one `kubeconfig_path`. A second cluster meant a second environment, and the `KUBECONFIG` variable overrides `kubeconfig_path` without an opt-in, so a shell pointing at another cluster silently redirected an apply. Issue #1539 asks for several clusters per environment. ADR-0024 already solved this for OPNsense firewalls with provider instances, and it is full of OPNsense specifics (HA pair check, `OPNSENSE_*`, `[name]` output prefixes). The new decisions are the deltas from it, so this is a new ADR, not a rewrite.

## Decision
Each extra Kubernetes cluster is a provider instance, as in ADR-0024. The primary cluster keeps the provider id `kubernetes`; every other one is `kubernetes@<name>`.

- **One registry:** `core/provider_instances.py` holds an `InstanceSpec(map_key, primary_key, selector_key, noun)` per instance-capable provider (`opnsense`: `firewalls`/`primary`/`firewall`; `kubernetes`: `clusters`/`primary`/`cluster`). The settings merge, the primary-only check, the shape check and the entry, file and manifest selection are generic helpers over it. A provider adds a spec instead of copying the code.
- **Config shape:** `provider_settings.kubernetes.clusters` maps a name to `kubeconfig_path` and `context`. `primary` names the primary and is required with more than one entry. There are no shared defaults. Combining `clusters:` with a top-level `kubeconfig_path` or `context` is an error.
- **Choosing a cluster for a resource**, most specific first: the entry's own `cluster:`, then a file-level `cluster:` beside `resources:` or the provider-centric list key, then the package manifest's `cluster:`, then the primary. Each selector key stamps only its own provider's resources, so a manifest `cluster:` never touches OPNsense resources and `firewall:` never touches Kubernetes ones. A blueprint package is pinned by the consuming package's manifest.
- **`KUBECONFIG`:** with a flat configuration it still overrides `kubeconfig_path`. Once `clusters:` is declared it is ignored for every cluster, the primary included, and a WARNING is logged once per process. This diverges from ADR-0024, where the primary-only rule covers `OPNSENSE_*`, which only apply behind `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE`. `KUBECONFIG` needs no opt-in, so honouring it for the primary would send its resources to whatever cluster the shell points at. The opt-in `<PROVIDER>_<KEY>` override stays primary-only.
- **`config_context`:** the generated `provider.tf` sets `config_context` from a `kubeconfig_context` variable (default empty, which renders `null`) in the `kubernetes` and `helm` blocks. Validation already honoured `context`, so Terraform and validation could point at different contexts. A flat configuration without `context` behaves as before.
- **Output references (ADR-0029):** dependencies are keyed by the exact provider id, so `kubernetes@cloud` reading `outputs.tailscale.*` orders `tailscale` first with no core change. The validator passes the instance id for the self-reference check, so a non-primary cluster may read `outputs.kubernetes.*` of the primary, and the primary still may not read its own. A non-primary instance as a producer is not supported: the reference grammar excludes `@` and `-`.
- **State identity:** no schema change and no migration. A flat configuration keeps provider `kubernetes`, `generated/<env>/terraform/kubernetes/` and its state. Converting it to `clusters:` keeps both, because the primary keeps the plain id. Instances use `kubernetes@<name>` rows and `terraform/kubernetes@<name>/`.
- **CLI:** a repeatable `--cluster <name>` on `infra plan|apply|destroy|doctor`, and `-P kubernetes` expands to the primary plus every declared cluster that has resources. `--cluster` is mutually exclusive with `-p` and `-r`, and combines with `--firewall`.

## Rationale
It reuses ADR-0024's observation that identity already hangs off the provider id (duplicate check, state rows, dependency graph, executor batches, reports), so no change to `ResourceConfig` or the state schema is needed. Extracting the registry now keeps a third instance-capable provider to a spec and its settings module.

Alternatives rejected:

- **Rewriting ADR-0024 generically.** It would blur what was decided for OPNsense when it was decided.
- **Honouring `KUBECONFIG` for the primary only, as ADR-0024 does for `OPNSENSE_*`.** That is the wrong-cluster bug this issue reports.
- **Allowing `kubernetes@<name>` as an output producer.** It needs the `outputs.*` grammar to accept `@` and `-`; left for a follow-up.

## Related Issues

- Issue #1539: support several kubernetes clusters per environment as provider instances

## Related Documentation

- [Kubernetes provider: several clusters per environment](../providers/kubernetes.md#several-clusters-per-environment)
- [ADR-0024: OPNsense firewalls are provider instances](0024-opnsense-firewalls-are-provider-instances-several-per-environment.md)
- [ADR-0029: Providers consume other providers' Terraform outputs](0029-providers-consume-other-providers-terraform-outputs-through-outputs-references.md)
