---
title: "ADR-0031: Secret references resolve from the owning package's secrets.yaml through a package prefix"
description: A package.<key> secret reference resolves only from the secrets.yaml of the package that defines the resource, through a per-package Terraform variable.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0031: Secret references resolve from the owning package's secrets.yaml through a package prefix

## Status
Accepted

## Context
A package keeps its secrets in a SOPS `secrets.yaml` next to its manifest. Those values merge into the package variables, so they are usable only as Jinja variables. The secret-backed fields (`terraform_secrets`, Kubernetes `string_data_secrets` and `data_secrets`, Helm `set_sensitive[*].value_secret`) resolve dotted references through the secrets bridge, and the bridge read only the environment's `secrets.yaml`. A service's secret could not live with its package, short of rendering it into a plain field and writing it in clear text into a generated `.tf` file (#1565).

## Decision
`package.` is a reserved prefix, like `outputs.` (ADR-0029). A `package.<key>` reference resolves against the `variables:` of the `secrets.yaml` of the package that defines the resource, and nothing else.

- **Scope:** it works in `terraform_secrets` of any provider and in the Kubernetes fields that fold into it. It never falls back to the env secrets file and never reaches another package. Unprefixed and `outputs.` references are unchanged. A top-level env secrets key named `package` can no longer be referenced.
- **Source:** the loader attaches the raw `secrets.yaml` variables to each resource it parses (`package_secrets`, excluded from dumps and reprs), with the package name and the package directory relative to `envs/<env>` (`package_path`). Raw values are used, never the merged manifest variables, so a manifest variable or default cannot satisfy a reference.
- **Naming:** the Terraform variable is `package_<slug(package_path)>_<key>`, the slug being the path lowercased with non-alphanumerics replaced by `_`. Two packages that use the same key get distinct variables. Naming is resource-aware (`secret_ref_tf_var`, `collect_terraform_secret_vars`), and a collision between two different sources raises.
- **Transport:** the value travels as `TF_VAR_*` through the existing bridge and the variable is declared `sensitive`. It is never written to a generated file or logged.
- **Errors:** plan-time validation and an apply-time backstop name the resource, the reference and the package, never a value, for a missing key, a missing `secrets.yaml`, an empty key, and a reference on a resource that is not from a package.

## Rationale
It reuses the secrets-to-`TF_VAR_*` bridge, so the secret never reaches a generated file, and it keeps a service's config and secrets together. The explicit prefix keeps existing configs unchanged and makes the source of each value visible in the YAML. The package directory, not the manifest name, identifies the package because manifest names are not unique across provider directories.

Alternative rejected: falling back from the env file to the package file for unprefixed references. It would make the source ambiguous and let a package secret shadow a shared one.

## Related Issues
- Issue #1565: resolve secret refs from the owning package's secrets.yaml
- Issue #1567: show secret sources in `infra doctor`

## Related Documentation
- [Infrastructure Packages: Per-Package Secrets](../configuration/infrastructure-packages.md#package-secret-references)
- [Validation: Secret Sources](../usage/validation.md#secret-sources)
- [Secrets Architecture](../architecture/secrets-architecture.md)
- [Kubernetes provider](../providers/kubernetes.md)
- [ADR-0029: Providers consume other providers' Terraform outputs through outputs references](0029-providers-consume-other-providers-terraform-outputs-through-outputs-references.md)
