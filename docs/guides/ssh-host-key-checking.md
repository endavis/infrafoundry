---
title: "SSH Host Key Checking"
description: "Record the host keys that package SSH connections now check, and fix a failed check"
audience:
  - users
tags:
  - guides
---

# SSH Host Key Checking

## Overview

Package SSH connections to long-lived hosts check the host key against your own `~/.ssh/known_hosts`. Nothing turns the check off and nothing records a key for you on first use. A host whose key is not recorded fails until you record it.

!!! warning "Breaking change"
    A jumphost, ESXi host, Proxmox node or Ansible target whose key is not in your `known_hosts` now fails. Record each key once, as described below, before the next `infra apply`.

## Affected Connections

| Connection | Checked against |
|------------|-----------------|
| Script handler hop to a package's `jumphost` (ssh, rsync, scp) | Your `known_hosts` |
| `infra doctor` jumphost preflight, SSH to the jumphost | Your `known_hosts` |
| ESXi OVF deployment, power on and destroy (`local-exec` over ssh) | Your `known_hosts` |
| ESXi config export | Your `known_hosts` |
| Proxmox appliance disk image VMs (`local-exec` ssh to the node) | Your `known_hosts` |
| Proxmox template image customization (`local-exec` ssh to the node) | Your `known_hosts` |
| Ansible runs for the `host` and `oci` providers (`host_key_checking = True`) | Your `known_hosts` |
| `infra doctor` jumphost preflight, SSH from the jumphost to a deployed VM | The keys the package pins in `ssh_known_hosts` |
| `foundry certs` install to a VM or instance: the jump hop | Your `known_hosts` |
| `foundry certs` install to a VM or instance: the VM itself | The keys the package pins |

The preflight skips a deployed VM that has no pinned key and prints a `foundry secrets host-keys --env <env>` hint. See [Blueprint VM host keys](../decisions/0032-blueprint-vms-get-pre-generated-ssh-host-keys-that-scripts-pin.md).

## Record a Host Key

Pick one way and check the fingerprint against one you trust (the host's console, your provider's portal, or the host's own `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`).

1. Connect once and confirm the fingerprint when ssh asks:

    ```bash
    ssh admin@host.example.com
    ```

2. Or scan the key, check its fingerprint, then append it:

    ```bash
    ssh-keyscan -t ed25519 host.example.com > /tmp/host.example.com.key
    ssh-keygen -lf /tmp/host.example.com.key
    cat /tmp/host.example.com.key >> ~/.ssh/known_hosts
    ```

Use the same name or address the package uses, such as `192.0.2.10` for an ESXi host or Proxmox node.

## A Changed Key

ssh reports `Host key for <host> has changed and you have requested strict checking`. Only if you know why the key changed (the host was reinstalled), remove the old entry and record the new key:

```bash
ssh-keygen -R host.example.com
```

If you do not know why, stop and find out first.

## Jumphost Preflight Probes

`infra doctor` probes deployed VMs from the jumphost against the keys the package pinned in its `ssh_known_hosts` variable. Run `foundry secrets host-keys --env <env>` to pin them.

## Rebuilding a Pinned VM

A VM pinned while it was deployed has only its public key recorded, so cloud-init cannot install a key on a rebuilt VM. Rebuild it in this order:

1. Destroy the VM (`foundry infra destroy --env <env>`).
2. Run `foundry secrets host-keys --env <env> --regenerate vm-01`.
3. Apply again (`foundry infra apply --env <env>`).

`infra plan` and `infra apply` stop with an error naming step 2 when it was skipped. A VM whose key was generated keeps it across rebuilds.

## Failure Messages

A failed apply or doctor run names the host and repeats these steps. ssh's own lines look like this:

```
No ED25519 host key is known for host.example.com and you have requested strict checking.
Host key verification failed.
```

Ansible runs stream their own `UNREACHABLE ... Host key verification failed` line; record the key as above.

## Related

- [SSH Authentication for Proxmox Operations](ssh-authentication.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)
