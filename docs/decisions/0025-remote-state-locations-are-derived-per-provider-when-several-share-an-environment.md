---
title: "ADR-0025: Remote state locations are derived per provider when several share an environment"
description: When two or more providers render a remote backend, each gets its own state location, with a pin and a placeholder to override.
date: 2026-11-17
audience:
  - contributors
tags:
  - adr
---

# ADR-0025: Remote state locations are derived per provider when several share an environment

## Status
Accepted

## Context
Every provider of an environment renders its own `backend.tf`, but the backend settings are one per environment. With a remote backend, all providers therefore pointed at one state key, so a second provider (or a second OPNsense firewall, [ADR-0024](0024-opnsense-firewalls-are-provider-instances-several-per-environment.md)) overwrote or locked against the first one's state. Issue #1464 asks for a state location per provider.

## Decision
The location is derived per provider, and only when it must be.

- **One provider renders a backend:** the configured location is used as written. Existing single-provider environments keep their state.
- **Two or more render a backend:** each gets the provider id inserted into the location field: a path segment before the last one for `s3` and `azurerm` `key`, a trailing segment for `gcs` `prefix`, a `-<slug>` suffix for `remote` `workspaces.name`, a `<slug>-` suffix for `workspaces.prefix` and a `_<slug>` suffix for `postgres` `schema_name`.
- **Pin:** `backend.bare_key_provider` names the one provider that keeps the configured location. It must be a provider that has resources in the environment.
- **Placeholder:** a `{provider}` token in the location field replaces the automatic rule entirely, for single and multi-provider environments alike.
- **Peer set:** the orchestrator computes it once per environment from the unfiltered resources and injects it into every provider, so `-P` never changes a key. `HostProvider` does not render a backend and is not a peer.
- **No state moves:** when the automatic rule moves a location, a warning names the provider, old and new location and the `terraform init -migrate-state` step. The local backend is untouched.

## Rationale
Deriving the key keeps the common single-provider case unchanged and makes the multi-provider case safe by default. The peer set comes from configured resources, so adding a second provider moves the first provider's key; the warning reports it, and `bare_key_provider` or `{provider}` give a stable location.

Alternatives rejected:

- **Always suffix the provider id.** Moves the state of every existing environment.
- **Require the operator to write one backend per provider.** Settings are per environment; it duplicates configuration and is what the bug already shows people forgetting.
- **Move state automatically.** `state backend migrate` is still a stub and an unattended state move is the riskier failure.

## Related Issues

- Issue #1464: providers in one environment share one remote terraform state key
- Issue #1450: several OPNsense firewalls per environment

## Related Documentation

- [State Management: several providers in one environment](../architecture/state-management.md#several-providers-in-one-environment)
- [ADR-0024: OPNsense firewalls are provider instances](0024-opnsense-firewalls-are-provider-instances-several-per-environment.md)
