---
title: "ADR-0022: Existing hosts are configured through a host provider and runner that never create or delete the machine"
description: Existing machines are configured by a host provider and HostRunner that run Ansible on apply and only forget the host on destroy
date: 2026-11-16
audience:
  - contributors
tags:
  - adr
---

# ADR-0022: Existing hosts are configured through a host provider and runner that never create or delete the machine

## Status
Accepted

## Context
Every resource type InfraFoundry manages has a create and delete lifecycle in some provider. Issue #1408 asks for machines that already exist and that no API can create or rebuild, such as a VPS on a long-term contract. They had to be configured by hand, or through a package with an `AFTER_APPLY` script that ran `ansible-playbook`, which leaves the host untracked (absent from `infra deployed`, not targetable with `-r` or `-P`) and cannot reuse the `tailscale:` block.

## Decision
Add a `host` provider with one resource type, `host`, and a provider-specific IaC runner, `HostRunner`, following the OPNsense pattern of [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md).

- **Provider:** `generate_host` writes an Ansible inventory, `ansible.cfg` and, when a host has a `tailscale:` block, a built-in enrollment playbook under `generated/<env>/ansible/host/`. `generate_terraform` writes only an empty `terraform {}` block. `get_terraform_resource_types` returns the pseudo prefix `host`, so outcomes with the address `host.<name>` fire the resource lifecycle events.
- **Runner:** `HostRunner` (`tool_name = "host_ansible"`, an IaC runner) acts only for the `host` provider. Apply runs `ansible-playbook --limit <host>` per host and playbook and returns a `ResourceOutcome` of `create` the first time and `update` once the host is in the managed set; the existing executor then records state and fires handlers. Destroy returns `delete` outcomes and never contacts the machine, so the existing destroy flow marks the rows `DELETED`, fires `on_destroy` and removes the tailnet device (#1401).
- **Tailscale:** the same `tailscale:` block, validated by `process_tailscale_config`. Enrollment runs at apply; `additional_parts` is an error. The auth secret reaches the enrollment run in one environment variable, never in the inventory or on controller disk.
- **Doctor:** schema checks, secret references and an SSH probe per host.
- **Out of scope:** drift detection. Removing a host from the YAML does not forget it; `infra destroy -r <host>` does.

## Rationale
The executor and destroy flow already track any runner outcome, so a runner that reports outcomes gets `infra deployed`, `-r`, `-P` and event handlers with no change to them. Making the host a resource, rather than a script, puts it under the same state and cleanup paths as cloud instances.

Alternatives rejected:

- **A package with a static inventory and a script handler.** The host stays untracked and the playbook is a shell wrapper; this is the workaround the issue set out to remove.
- **The generic `AnsibleRunner`.** It is not an IaC runner, runs only as an event handler and runs one `playbook.yml` for the provider, so it neither reports per-host outcomes nor limits a run to a host.
- **A `ProviderBase` capability to skip Terraform.** It would change the shared provider contract for one provider, and an empty `terraform {}` block, as OPNsense writes, already makes the Terraform runner a no-op.

## Related Issues

- Issue #1408: manage existing hosts that no provider creates
- Issue #1401: remove an instance's tailnet device when it is destroyed

## Related Documentation

- [Host provider](../providers/host.md)
- [Tailscale provider](../providers/tailscale.md)
