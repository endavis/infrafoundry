---
title: "ADR-0028: OpenWrt devices are managed through generated community.openwrt playbooks with ubus apply-rollback"
description: OpenWrt devices are managed by generated community.openwrt playbooks that a dedicated Ansible runner checks, applies with ubus rollback and confirms, instead of a native runner or the generic Ansible runner
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0028: OpenWrt devices are managed through generated community.openwrt playbooks with ubus apply-rollback

## Status
Accepted

## Context
Issue #1482 asks for OpenWrt devices (stock OpenWrt and vendor builds such as GL.iNet) to be managed by InfraFoundry: static leases, port forwards, DHCP pools and interface addresses. MikroTik RouterOS is managed natively over its REST API by a direct runner (ADR-0026), because RouterOS applies each REST call at once, so a multi-step change can lock the controller out half way and the provider must order the writes itself.

OpenWrt differs in three ways, measured against a GL.iNet router running OpenWrt 23.05 with the `community.openwrt` collection:

- UCI stages changes and commits them together, so there is no phased-ordering hazard.
- The collection's check mode with `--diff` gives a value-level plan, and a converged device plans clean.
- `ubus` offers apply with rollback and a confirm call, so a change that cuts the controller off reverts on its own.

The existing generic `AnsibleRunner` cannot carry the provider. It is not an IaC runner, so the orchestrator skips it on `infra plan` and `infra apply` (as ADR-0022 already found). It runs one `playbook.yml` per provider without `--diff`, returns no per-resource outcomes, has no destroy and is not drift-detectable. Making it an IaC runner would start running the `playbook.yml` that other providers write on every apply.

## Decision
Add an `openwrt` provider that generates a playbook for the `community.openwrt` collection, and a dedicated `OpenWrtAnsibleRunner` (`tool_name = "openwrt_ansible"`) that runs it.

- **Runner.** The runner shells out to `ansible-playbook` and the same collection as any Ansible use, but is a thin IaC runner modelled on the host and MikroTik runners. It runs `openwrt.yml` only, never `playbook.yml`. `plan` runs `--check --diff` with `ANSIBLE_STDOUT_CALLBACK=ansible.posix.json` and reads the per-task JSON. `apply` runs that check pass first and refuses a plan that could cut the management connection, then runs the playbook for real. The runner returns per-resource outcomes, released managed rows, and is drift-detectable through the direct-runner path of the drift detector. The generic `AnsibleRunner` is unchanged.
- **Playbook.** Built as Python dicts and dumped with `yaml.safe_dump`, never from a text template, and text values reject control characters and Jinja markers. Every write is `command: section` with `replace: false`, so options set in the vendor UI survive. Static leases match by MAC and are created anonymous, so a lease made in the UI is adopted and never renamed; guards fail the run on duplicate or other-case MACs.
- **Commit.** The playbook stages UCI changes without committing, replays them into an rpcd session with a ucode helper through the ubus `uci` API, runs `ubus call uci apply` with rollback, reconnects, and sends `ubus call uci confirm`. A device that cannot be reached afterwards reverts on its own. If the run fails before the apply was reached, a rescue reverts the staging. A preflight refuses to run when changes are already pending.
- **Management safety.** A change to a `network.interface` that affects the subnet of the settings address is refused at plan time unless the resource sets `confirm_management_change: true`. A port forward that covers the SSH port on the WAN needs the same flag.
- **Provider-declared collections.** `ProviderBase.ansible_collection_requirements()` returns the collections a provider needs, empty by default. `RequirementsManager` merges them with the blueprint requirements for the providers that have resources in scope, so `foundry deps check` and `deps sync` handle `community.openwrt`. The change is additive: an optional `providers` argument, and a defaulted `providers` field on `RequirementStatus`.
- **One device per environment**, under `provider_settings.openwrt`, following the MikroTik precedent. Several devices per environment (the OPNsense instance model of ADR-0024) are a follow-up.
- **Managed set (ADR-0018).** Only `dhcp.host` and `firewall.redirect` are deleted; `network.interface` and `dhcp.pool` are only forgotten.

## Rationale
A native SSH runner would reimplement the UCI matching, diff and check-mode logic that the collection already provides and tests against real OpenWrt containers. A dedicated runner keeps the generic Ansible runner's behaviour for the providers that depend on it, and gives the openwrt provider the outcome, destroy and drift contract it needs. ADR-0026's phased writes exist because RouterOS applies each call at once; UCI plus ubus rollback gives the same lock-out protection without the controller ordering anything.

Finding: handing the staged files to the session by copying them into rpcd's save directory works on a vendor build based on OpenWrt 23.05 but not on stock OpenWrt 25.12, where rpcd no longer names that directory after the session id and does not expose it. Replaying the staged changes through the public ubus API uses no rpcd internals. With the replay, `infra apply` was verified on stock OpenWrt 25.12.6: changes, deletes and restores were confirmed and outlasted the rollback timeout, and an unreachable management-address change rolled back by itself. On a GL.iNet device running OpenWrt 23.05, `infra apply` with the replay was verified (change, confirm, restore, clean re-plan). Which services reload on apply was not measured and is not claimed. A confirmed management-address change that reconnects to the new address was verified on stock 25.12.6; the reconnect checks the host key under the settings address (ssh `HostKeyAlias`), so strict host-key checking stays on across the address change.

## Related Issues

- Issue #1482: manage OpenWrt devices over SSH
- Issue #1481: read-only collectors for unmanaged devices (ADR-0027)

## Related Documentation

- [OpenWrt provider](../providers/openwrt.md)
- [ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md)
- [ADR-0022](0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md)
- [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)
