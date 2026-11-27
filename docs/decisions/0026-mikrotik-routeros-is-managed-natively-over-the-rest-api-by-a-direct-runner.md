---
title: "ADR-0026: MikroTik RouterOS is managed natively over the REST API by a direct runner"
description: MikroTik RouterOS is managed over its REST API by a provider-specific direct runner that plans phased, lock-out-safe changes
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0026: MikroTik RouterOS is managed natively over the REST API by a direct runner

## Status
Accepted

## Context
Issue #1480 asks for a MikroTik RouterOS provider, first for a managed switch whose bridge VLAN filtering must be configured without locking the operator out. RouterOS exposes a REST API (RouterOS 7 and later) that mirrors its console paths: the resource type `interface.bridge.port` is `/rest/interface/bridge/port`. Two designs were considered: generate Terraform for a community RouterOS provider, or manage the device natively over REST.

## Decision
Add a `mikrotik` provider with seven resource types (`interface.bridge`, `interface.bridge.port`, `interface.bridge.vlan`, `interface.vlan`, `ip.address`, `ip.dhcp-client`, `ip.service`) and a provider-specific IaC runner, `MikroTikRestRunner` (`tool_name = "mikrotik_rest"`), following the direct-runner pattern of [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) and [ADR-0022](0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md). The provider's Terraform output is an empty `terraform {}` block.

- **Read-diff-write.** The runner reads each REST path, compares only the fields the YAML declares after normalizing RouterOS's string values, and plans create, update and delete changes. Objects are matched by a natural key (bridge name, port interface, address CIDR, and so on), so an object that already exists on the device is adopted with no import step. Dynamic rows are ignored. `ip.service` rows are update-only.
- **Deletes.** An object is deleted only when the YAML says `absent: true`, or when InfraFoundry applied it before and the YAML no longer declares it (the managed set, [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). Any other live object is reported as `unmanaged (kept)`. Filtered runs and drift runs are add-only.
- **Phased apply order.** The plan computes phases: A disables VLAN filtering on bridges going from on to off; B creates in dependency order (and widens bridge VLAN membership to the union of old and new); C enables VLAN filtering; D narrows membership and changes PVIDs on filtering bridges; E deletes in reverse dependency order; F updates `ip.service`. Changes that touch the live management path sort last within D and E.
- **Lock-out refusal.** The plan computes the end state and refuses when the management address (the host of `api_url`) would have no on-link address, a bridge slave management interface, a management VLAN missing from the bridge VLAN table or without a member port, no port on the bridge PVID, or when the `ip.service` the provider connects through would be disabled or moved off the `api_url` port.
- **Drift.** The runner implements `DriftDetectable`; `DriftDetector` uses an IaC runner that is drift-detectable and is neither Terraform nor OpenTofu when the provider offers a `generate_<tool>` method for it. OPNsense keeps its Terraform path because its runner is not drift-detectable.
- **Scope.** One device per environment, from `provider_settings.mikrotik`. The first change (#1480) shipped the plan, validation, doctor checks and drift; #1483 adds apply and destroy. Apply stops at the first error and reports the failed step and the completed ones. Destroy deletes only the declared, deletable objects that exist live (never `ip.service`, `absent: true` entries, undeclared rows, or built-in and dynamic rows) and refuses whole when the end state would remove the management path.

## Rationale
Terraform applies one dependency graph, in parallel, with no phases. The safe sequence needs phases (add paths, then enable filtering, then narrow membership and change PVIDs, then delete), and ports and VLAN entries reference the bridge, so making the bridge's filtering flag depend on them is a cycle. A native runner owns the order and can refuse an unsafe end state at plan time. A device that is already configured (default bridge, ports, factory address, built-in services that can only be updated) needs an import per object under Terraform, while a read-diff-write engine adopts live objects by key. `requests` is already a dependency, so no package is added, and the diff and ordering logic are pure functions tested against an in-memory fake device.

Alternatives rejected:

- **Generated Terraform for a community RouterOS provider.** It cannot express "filtering last" in one apply, needs an import per existing object, and cannot refuse a lock-out at plan time.
- **Ansible `community.routeros`.** It configures but offers no plan or diff, so it has no parity with `infra plan` and drift detection.

Cost: drift detection needed a small additive dispatch in `DriftDetector`, since direct runners were not drift-detectable before. The write verbs (PUT, PATCH, DELETE) follow RouterOS REST conventions and are unit-tested against an in-memory fake device and were verified live on a RouterOS CHR virtual machine (#1483, #1485).

## Related Issues

- Issue #1480: add a MikroTik RouterOS provider
- Issue #1483: apply and destroy for the MikroTik provider
- Issue #1485: RouterOS CHR test blueprint, the live verification target
- Issue #1489: record the live verification in the docs
- Issue #1710: bootstrap https with a self-signed certificate resource

## Related Documentation

- [MikroTik provider](../providers/mikrotik.md)
- [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md), [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md), [ADR-0022](0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md), [ADR-0023](0023-infra-plan-runs-providers-offline-validation-live-checks-stay-in-infra-doctor.md), [ADR-0024](0024-opnsense-firewalls-are-provider-instances-several-per-environment.md)
- [ADR-0037: MikroTik RouterOS is upgraded to the latest release of a channel by a provider command](0037-mikrotik-routeros-is-upgraded-to-the-latest-release-of-a-channel-by-a-provider-command.md)
