---
title: "Validation and Pre-Flight Checks"
description: "The three tiers of validation that run before plan and apply"
audience:
  - users
tags:
  - usage
---

# Validation and Pre-Flight Checks

## Overview

InfraFoundry provides a three-tier validation system to catch configuration, reference, and connectivity issues **before** `foundry infra plan` or `foundry infra apply`, keeping deployments safe and predictable.

## Audience and Prerequisites

- **Audience:** Operators and CI pipelines running plan/apply workflows.
- **Prerequisites:** Config repo available, `foundry` installed via `uv`, provider credentials and network access for targeted environments.

## When to Use This

- Before any plan/apply, especially for production changes.
- After editing settings, resources, or secrets to ensure structural integrity.
- In CI to block merges when validation fails.

## Three-Tier Doctor System

InfraFoundry validation is organized into three levels, each checking a different scope:

| Level | Command | What It Checks |
|-------|---------|----------------|
| **System** | `foundry doctor` | Binary dependencies (Terraform, OpenTofu, Ansible, SOPS, Age) |
| **Config** | `foundry config doctor [--deep]` | Config repo structure, environments, state backend, SOPS keys, state/filesystem consistency, blueprint validation |
| **Infrastructure** | `foundry infra doctor --env <env>` | Provider API connectivity, nodes/hosts, storage pools, network bridges, templates, resource IDs, MAC conflicts, and the jumphost of packages that set one |

## Quick Start

```bash
# Check system dependencies
foundry doctor

# Check config repo health
foundry config doctor --deep

# Validate against provider APIs
foundry infra doctor --env dev
foundry infra doctor --env dev --resource vm-01 --resource vm-02
foundry infra doctor --env prod --package k3s-cluster
foundry infra doctor --env dev --verbose
```

## Jumphost Preflight

A package that sets `jumphost` runs its blueprint scripts on that host, and the scripts SSH to the package's VMs with the jumphost's own ssh-agent. If the agent holds no key, or not the one the VMs accept, the apply only fails minutes later, after terraform has created the VMs. `infra doctor` checks the jumphost first, once per jumphost, in a single SSH session opened the same way the script handler opens it:

```
Jumphost preflight (ansible@ansible.endavis.net):
  [OK] SSH to jumphost
  [OK] ssh-agent: 1 key(s) loaded
  [SKIP] key match: package declares no public key to compare
  [OK] tools: rsync, bash, python3, ssh, scp
  [OK] writable /tmp
  [OK] target k3s-server (192.168.10.70): not deployed; routable and unused
  [OK] target k3s-agent-1 (192.168.10.71): not deployed; routable and unused
  [OK] target k3s-agent-2 (192.168.10.72): not deployed; routable and unused
  [OK] target k3s-agent-3 (192.168.10.73): not deployed; routable and unused
  [OK] output ~/.kube/k3s-homelab.yaml: exists, writable
Jumphost preflight: 9 OK, 1 SKIP
```

| Check | Fails when |
|-------|-----------|
| SSH to jumphost | The jumphost can't be reached non-interactively (BatchMode). The remaining checks are skipped. |
| ssh-agent | `ssh-add -l` finds no keys (exit 1) or no agent (exit 2). |
| key match | A public key the package declares (`ssh_public_key`, or a VM's `ssh_keys`) is not in the agent. Comments are ignored. `SKIP` when the package declares none, for example when the key comes from a cloud-init snippet. |
| tools | `rsync`, `bash`, `python3`, `ssh` or `scp` is missing on the jumphost. |
| writable /tmp | The script handler can't create its work directory in `/tmp`. |
| target (deployed) | SSH from the jumphost to the VM fails. The detail carries ssh's last error line, such as `Permission denied (publickey)`. |
| target (not deployed) | The jumphost has no route to the IP, or something already answers a ping there, which means another host holds the address. `WARN` when `ip` is missing on the jumphost. |
| output | Only `WARN`: an `outputs:` destination doesn't render, isn't absolute, or can't be written on the workstation. An apply only warns about these too. |

**Targets** are the package's VMs that have a DHCP reservation whose `hostname` is the VM name; the reservation gives the IP. A VM counts as deployed when its newest state-DB row, ignoring the `planned` rows every `infra plan` adds, is `active` or `updating`; `deleted` or no row means not deployed, and anything in between is `SKIP`. Target SSH runs as the package's `ssh_user`, else the user in `jumphost`, with the blueprint scripts' options (`StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null`). Leftover `known_hosts` entries on the jumphost therefore can't break an apply and aren't checked.

Any `FAIL` makes doctor exit 1, so `foundry infra doctor --env prod -p k3s-cluster && foundry infra apply --env prod -p k3s-cluster` stops before the apply.

## Additional Validation Commands

Beyond the doctor commands, InfraFoundry offers additional validation tools:

- **`foundry infra test --env <env>`** -- Run infrastructure tests against configurations (duplicate names, missing references, configuration problems).
- **`foundry infra security --env <env>`** -- Scan generated Terraform/Ansible for security issues using Checkov.
- **`foundry infra analyze dependencies --env <env>`** -- Verify dependency graph is acyclic and references resolve.

## Examples

- **Pre-deployment validation:**
  ```bash
  foundry config doctor --deep
  foundry infra doctor --env prod
  foundry infra test --env prod
  ```
- **CI usage (GitHub Actions excerpt):**
  ```yaml
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        - run: foundry config doctor --deep
        - run: foundry infra doctor --env prod
        - run: foundry infra test --env prod
  ```

## Related Documentation

- [CLI Reference](cli-reference.md)
- [Settings File Structure](../configuration/settings-file-structure.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [State Management](../architecture/state-management.md)

## Troubleshooting

- **Symptom:** Missing templates/networks in doctor output. **Fix:** Create the resource in the provider or update the configuration reference; rerun `foundry infra doctor --env <env>`.
- **Symptom:** Doctor reports API failures. **Fix:** Verify endpoints, tokens, kubeconfig, and network reachability; test with provider CLIs.
- **Symptom:** `[FAIL] ssh-agent: agent is running but has no keys loaded`. **Fix:** On the jumphost, load the key the VMs accept into the agent the jumphost user's non-interactive SSH sessions use (for example with `ssh-add` or keychain), then rerun doctor.
- **Symptom:** Unknown resource/provider. **Fix:** Confirm resource type spelling and provider availability in the current framework version.

---

Last updated: 2026-04-13 GMT


---
[Back to Table of Contents](../index.md)
