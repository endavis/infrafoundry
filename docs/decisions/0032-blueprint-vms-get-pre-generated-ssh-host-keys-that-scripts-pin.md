---
title: "ADR-0032: Blueprint VMs get pre-generated SSH host keys that scripts pin"
description: InfraFoundry generates an ed25519 host key per blueprint VM, cloud-init installs it, and the blueprint scripts verify the VM against the pinned public key.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0032: Blueprint VMs get pre-generated SSH host keys that scripts pin

## Status
Accepted

## Context
A blueprint script that reaches a VM it has just built over SSH has no key to check the VM against: the VM generates its host key on first boot. The scripts therefore turned host key checking off (`StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null`) for the VM, and a host answering on the VM's address was trusted. The scripts send credentials and fetch certificates over those connections (#1581).

## Decision
InfraFoundry generates one ed25519 host key pair per blueprint VM ahead of time and the scripts pin the public half.

- **Opt-in:** a Proxmox VM resource sets `ssh_host_key: {address: <address the scripts use>}`. The aiqum, console-connector and k3s-cluster (Proxmox) blueprints do.
- **Storage:** the pair is kept in the owning package's SOPS `secrets.yaml` under the reserved key `variables.ssh_host_keys.<resource-name>.{ed25519_private, ed25519_public}`. The loader keeps `ssh_host_keys` out of the merged package variables (ADR-0031 `package_secrets` only), so a private key never reaches script env, Jinja contexts or events.
- **Derived variable:** the loader sets the scalar package variable `ssh_known_hosts`, `;`-separated `<name>,<address> ssh-ed25519 <key>` lines built from the public keys. It is a scalar so event `env:` blocks survive their JSON rendering.
- **Delivery:** when a private key exists, the Proxmox provider adds a `package.ssh_host_keys.<name>.ed25519_private` reference to `terraform_secrets` (ADR-0031) and appends an `ssh_keys:` fragment to the VM's cloud-init user data that holds a `jsonencode(var.<name>)` expression, never the value. cloud-init installs the key at first boot.
- **Verification:** the scripts write `ssh_known_hosts` to a private temporary file and connect with `StrictHostKeyChecking=yes`, `UserKnownHostsFile=<file>` and `GlobalKnownHostsFile=/dev/null`. The hop to a jumphost is strict against the operator's own `known_hosts`; the file is staged on the jumphost for the inner hop and removed on exit. A key mismatch stops the script at once and names the VM.
- **Generation:** `foundry secrets host-keys --env <env>` (not plan time, which stays read-only and offline, ADR-0023) generates keys with `ssh-keygen` in a private temporary directory and writes them with `sops set --value-stdin`, so no key is on a command line or in a plaintext file.
- **Existing VMs:** the command reads the state database. A deployed VM is pinned: the key it presents now is recorded (`ssh-keyscan`, from the package's jumphost when one is set) and only `ed25519_public` is stored, so no cloud-init data, snippet file or VM changes. An undeployed VM gets a generated pair. A VM that is being created, deleted or in error is refused. `--regenerate <name>` replaces a key only for a VM that is not deployed. Pinning a deployed VM is a one-time recording; it trusts the key the VM presents at that moment.
- **OCI instances (#1583):** the opt-in also covers OCI `instance` resources with a `tailscale:` block (the k3s-cluster OCI variant); `ssh_host_key` on an instance without `tailscale:` is a validation error. Delivery is an extra `text/cloud-config` part in the Tailscale module's `additional_parts`, added only when a private key exists, so a pinned instance keeps its `user_data` and is not replaced. Existing nodes are pinned by scanning `<node>.<tailnet>` from where the scripts run (the jumphost when the package sets one, otherwise locally). Ansible runs with `ANSIBLE_HOST_KEY_CHECKING=True` and `ANSIBLE_SSH_COMMON_ARGS` pointing at the pinned file; the OCI scripts connect directly over the tailnet, so no file is staged anywhere.
- **Breaking change:** a package that uses these blueprints fails `infra plan` until `foundry secrets host-keys` has been run. The error names the command.

## Rationale
Pre-generated keys give the scripts a value to check from the first connection, with no trust-on-first-use window. Provider-API fingerprints were rejected because not every guest reports them and the API itself would become the trust root. Generating at plan time was rejected because plan is read-only and offline, and only the operator holds the age key. Pinning a deployed VM instead of rebuilding it keeps an upgrade from replacing running VMs.

Exposure: the private key reaches Terraform state (`proxmox_virtual_environment_file` `source_raw.data`, under `generated/<env>/terraform/proxmox/` with the local backend) and the Proxmox snippet storage, as any cloud-init content does. It never reaches generated `.tf` files, tfvars, inventories, logs or outputs, and the plan shows `(sensitive value)`. Use an encrypted remote backend.

Live-check findings for OCI (#1583):

- Port 22 on a tailnet address is answered by Tailscale SSH, while OpenSSH still listens on all addresses.
- The ed25519 key Tailscale SSH presents is the node's `/etc/ssh/ssh_host_ed25519_key.pub`. tailscaled keeps no host keys of its own, so cloud-init `ssh_keys` is enough and no `write_files` is needed.
- `ssh-keyscan -t ed25519 <node>.<tailnet>` returns that key.

OCI exposure: the private key reaches Terraform state (the Tailscale module's data source and `oci_core_instance.metadata.user_data`) and OCI instance metadata, which anyone with instance read rights on the OCI API can read and which any process on the node that can reach the metadata service (including k3s pods) can read. The Tailscale OAuth secret already travels the same way, so this adds no new channel.

Out of scope: OCI instances without `tailscale:`, and the other SSH call sites in the framework (handler and preflight jumphost connections, ESXi, the Proxmox node snippet upload).

The other SSH call sites (handler and preflight jumphost connections, ESXi, Proxmox) are covered by [ADR-0033](0033-package-ssh-connections-check-host-keys-against-the-operators-known-hosts.md).

## Related Issues
- Issue #1581: pin pre-generated ssh host keys for VMs built by blueprints
- Issue #1583: the same for k3s-cluster on OCI over Tailscale SSH (OCI instances with `tailscale:`)
- Issue #1648: the aiqum certificate export reads the served certificate over this pinned channel
- Issue #1630: a public-key-only pin needs --regenerate between destroy and rebuild; plan/apply catch it

## Related Documentation
- [Infrastructure Packages: SSH Host Keys](../configuration/infrastructure-packages.md#ssh-host-keys)
- [Secrets Architecture: SSH host keys](../architecture/secrets-architecture.md#ssh-host-keys)
- [CLI Reference: secrets host-keys](../usage/cli-reference.md#secrets-host-keys)
- [ADR-0031: Secret references resolve from the owning package's secrets.yaml through a package prefix](0031-secret-references-resolve-from-the-owning-packages-secretsyaml-through-a-package-prefix.md)
