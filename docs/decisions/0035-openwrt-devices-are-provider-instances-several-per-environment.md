---
title: "ADR-0035: OpenWrt devices are provider instances, several per environment"
description: Each extra OpenWrt device is a provider instance openwrt@name, selected by a device key, and the primary keeps the plain openwrt id
date: 2026-11-24
audience:
  - contributors
tags:
  - adr
---

# ADR-0035: OpenWrt devices are provider instances, several per environment

## Status
Accepted

## Context
An environment could address one OpenWrt device: `provider_settings.openwrt` held one `address`. Issue #1656 asks for several devices per environment, targeted the way OPNsense resources target a firewall. ADR-0028 deferred this to the instance model of ADR-0024, and ADR-0030 generalised that model into `InstanceSpec`. The new decisions are the deltas from both, so this is a new ADR, not a rewrite.

## Decision
Each extra OpenWrt device is a provider instance. The primary device keeps the provider id `openwrt`; every other one is `openwrt@<name>`.

- **Spec:** `INSTANCE_SPECS["openwrt"] = InstanceSpec("devices", "primary", "device", "device", exclusive_selector=False)`.
- **Config shape:** `provider_settings.openwrt.devices` maps a name to an entry. `address` is the only per-device key and cannot be a top-level value once `devices:` is declared. `ssh_user`, `ssh_port`, `ssh_private_key_file`, `rollback_timeout` and `connect_timeout` are shared defaults that an entry overrides. `primary` is required with more than one entry. The flat shape is unchanged.
- **Non-exclusive selector:** `device` is also an ordinary field of other providers' entries (Tailscale `device_subnet_routes` and `device_tags`, OPNsense VLANs and interface assignments). `InstanceSpec.exclusive_selector` is `False` for OpenWrt, so `entry_instance_provider` skips a `device` key on an entry whose own provider does not honour it. `firewall` and `cluster` keep the strict "only supported for provider" error. Without this, a Tailscale entry with a top-level `device:` and no `config:` key would stop loading.
- **Choosing a device for a resource**, most specific first: the entry's `device:`, a file-level `device:` beside `resources:`, the package manifest's `device:`, then the primary. The file-level selector keys are read by one helper, `file_selections`, instead of a hard-coded `cluster` in three loaders. Provider-centric files are out of scope, because OpenWrt types are dotted and the provider requires the resource-centric format.
- **Environment overrides:** OpenWrt reads no `OPENWRT_*` variables and writes no Terraform variables, so ADR-0024's primary-only rule has nothing to apply to.
- **State identity:** no schema change. A flat configuration keeps provider `openwrt` and `generated/<env>/ansible/openwrt/`; converting to `devices:` with the same primary keeps both. Other devices use `openwrt@<name>` rows and `ansible/openwrt@<name>/`, so each device has its own inventory with `HostKeyAlias=<that device's address>`, and ADR-0032's pinned host key applies per device.
- **CLI:** `-P openwrt` expands to the primary plus every declared device that has resources. There is no `--device` option; it would add an option to four commands and can follow the way `--cluster` did.
- **Output:** `infra doctor` prefixes each device's results with `[<name>] ` and the runner prints `openwrt_ansible[<name>]`, only when `devices:` is declared.

## Rationale
Identity already hangs off the provider id (ADR-0024), the registry already exists (ADR-0030), and the provider's runner, per-id output directories and executor batches are per id. Adding a spec and resolving settings per provider id is the whole change, and later work that needs a device (a firmware upgrade command, #1655) can address it by provider id.

Alternatives rejected:

- **Rewriting ADR-0028 or ADR-0024.** It would blur what was decided when it was decided.
- **A distinct selector name such as `openwrt_device`.** It avoids the field collision, but reads less naturally, and the issue asks for devices to be targeted the way OPNsense resources target a firewall.

## Related Issues

- Issue #1656: manage several OpenWrt devices per environment
- Issue #1655: OpenWrt firmware work addresses a device by provider id
- Issue #1482: manage OpenWrt devices over SSH (ADR-0028)

## Related Documentation

- [OpenWrt provider: Several devices per environment](../providers/openwrt.md#several-devices-per-environment)
- [ADR-0024: OPNsense firewalls are provider instances](0024-opnsense-firewalls-are-provider-instances-several-per-environment.md)
- [ADR-0028: OpenWrt devices are managed through generated playbooks](0028-openwrt-devices-are-managed-through-generated-communityopenwrt-playbooks-with-ubus-apply-rollback.md)
- [ADR-0030: Kubernetes clusters are provider instances](0030-kubernetes-clusters-are-provider-instances-several-per-environment.md)
