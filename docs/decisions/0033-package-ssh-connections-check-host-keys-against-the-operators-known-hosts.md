---
title: "ADR-0033: Package SSH connections check host keys against the operator's known_hosts"
description: Package SSH connections to jumphosts, ESXi hosts and Proxmox nodes check the host key against the operator's known_hosts, and generated Ansible configs enable host key checking.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0033: Package SSH connections check host keys against the operator's known_hosts

## Status
Accepted

## Context
Package SSH connections to long-lived hosts (jumphosts, ESXi hosts, Proxmox nodes) and the generated Ansible configuration for the `host` and `oci` providers turned host key checking off: `StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null` and `host_key_checking = False`. Any host answering on the address was trusted. ADR-0032 fixed this for blueprint VMs and their scripts only (#1588).

## Decision
Every package SSH connection to a long-lived host checks the host key strictly against the operator's own `known_hosts`.

- **No trust on first use:** no `/dev/null` known_hosts file and no `accept-new`. A host whose key is not recorded fails until the operator records it.
- **One definition:** `core/ssh_options.py` holds the option (`StrictHostKeyChecking=yes`). Python call sites import the constant; Jinja templates read the `ssh_host_key_opts` global that `TemplateRendererMixin` registers.
- **Call sites:** the script handler's jumphost transport (ssh, rsync, scp), the `infra doctor` jumphost preflight, the ESXi OVF template and exporter, and the Proxmox appliance disk image `local-exec` ssh.
- **Preflight VM probes:** the probe from the jumphost to a deployed VM runs strictly against the package's pinned `ssh_known_hosts`, staged in a private temporary file with `HostKeyAlias=<vm name>`. A VM with no pinned key is skipped with a `foundry secrets host-keys` hint.
- **Ansible:** the generated `ansible.cfg` for the `host` and `oci` providers sets `host_key_checking = True`.
- **Failure message:** `host_key_hint` recognises ssh's own strict-checking messages and adds one fixed message naming the host and how to record its key.
- **Out of scope:** the OPNsense interface assignment installer uses `StrictHostKeyChecking=accept-new` for a firewall it has just installed on; changing it is a separate decision.
- **Breaking change:** a jumphost, ESXi host, Proxmox node or Ansible target whose key is not in the operator's `known_hosts` now fails until its key is recorded.

## Rationale
Trusting whatever answers lets a host on the path read credentials and receive commands. The operator's `known_hosts` is the one place the operator already records trust, and it needs no new storage. Trust on first use was rejected because the first connection is the one an attacker would answer. Keeping the option in one module stops the call sites from drifting apart again.

## Related Issues
- Issue #1588: check ssh host keys for package connections to jumphosts, ESXi and Proxmox hosts
- Issue #1581: pin pre-generated ssh host keys for VMs built by blueprints (ADR-0032)

## Related Documentation
- [SSH Host Key Checking](../guides/ssh-host-key-checking.md)
- [Validation and Pre-Flight Checks: Jumphost Preflight](../usage/validation.md#jumphost-preflight)
- [ADR-0032: Blueprint VMs get pre-generated SSH host keys that scripts pin](0032-blueprint-vms-get-pre-generated-ssh-host-keys-that-scripts-pin.md)
