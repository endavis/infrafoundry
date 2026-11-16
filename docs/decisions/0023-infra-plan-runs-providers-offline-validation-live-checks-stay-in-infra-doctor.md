---
title: "ADR-0023: infra plan runs providers' offline validation; live checks stay in infra doctor"
description: Plan and apply run each provider's network-free validation, and live checks stay in infra doctor
date: 2026-11-16
audience:
  - contributors
tags:
  - adr
---

# ADR-0023: infra plan runs providers' offline validation; live checks stay in infra doctor

## Status
Accepted

## Context
`infra plan` and `infra apply` ran no provider validation. Errors a validator already knew how to find, such as a bad `terraform_secrets` reference or a malformed `tailscale:` block, surfaced only in `infra doctor`, or after generation or a runner had started. Issue #1433 asks for plan to run them. `validate_references` cannot be called as is: it reaches the network for most providers (OPNsense makes four live GETs and returns early without credentials, Proxmox builds an API client, the host provider probes every host over SSH), and a host that Proxmox creates earlier in the same apply cannot be reached at plan time.

## Decision
Split validation into an offline part, run on plan, and a live part, kept in doctor.

- **Contract:** an optional, runtime-checkable `ValidatesOffline` protocol in `core/protocols.py` with `validate_offline(resources, reference_resources, env_config, report)`. It must make no network or subprocess calls and checks a subset of `validate_references`. `ProviderBase` does not change, and each provider's `validate_references` calls its offline part, so doctor runs the same checks.
- **Where it runs:** `PlanOrchestrator.plan` runs one pass over the provider batches after the provider and resource filters and the policy check, and before any hook, state write or runner call. `apply` inherits it through `plan`.
- **Result:** warnings are printed and the plan continues. Errors raise `ConfigValidationError` (IF-VALIDATION-007), mark the deployment FAILED and emit `PLAN_FAILED`. A validator that crashes becomes a warning, so a validator bug cannot block deploys.
- **Doctor-only:** `validate_connectivity`, every live reference check and the host SSH probe. OPNsense endpoint support is not repeated, because its runner's plan already checks it.

## Rationale
New provider validation must be placed deliberately: network-free checks go in `validate_offline`, live ones stay in `validate_references`. A false-positive error in an offline validator blocks plan and apply, so it is a validator bug to fix, not something to bypass.

Alternatives rejected:

- **Calling `validate_references` on plan.** It adds API calls, runs OPNsense endpoint support twice, and the host SSH probe would fail every first apply.
- **A `--skip-validation` flag.** The checks are deterministic config checks that doctor already treats as errors, and a flag would change the CLI signature.

## Related Issues

- Issue #1433: run provider validation as part of infra plan
- Issue #1435: wire Kubernetes validation into doctor and plan
- Issue #1133: validate references against resources outside a filter

## Related Documentation

- [Validation](../usage/validation.md)
- [Implementing providers](../development/implementing-providers.md)
