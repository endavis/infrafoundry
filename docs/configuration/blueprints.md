# Configuration Blueprints Guide

## Overview

Blueprints are template projects that scaffold new InfraFoundry configuration repositories or services with best practices baked in.

## Audience and Prerequisites

- **Audience:** Operators and platform teams standardizing configuration patterns.
- **Prereqs:** InfraFoundry installed (`foundry`), access to built-in or custom blueprints, and a target directory to create into.

## When to Use This

- Bootstrapping a new config repo or service quickly.
- Enforcing consistent structure across teams/tenants.
- Sharing common patterns for VMs, networks, or multi-provider stacks.

## Quick Start

```bash
foundry config new create basic-vm ./my-new-vm
```

## Configuration Details

- **Command:** `foundry config new create <blueprint-name> <target-directory>`.
- **Built-in location:** `blueprints/` at the framework repo root.
- **Blueprint contents:** `blueprint.yaml` metadata + Jinja2-templated resource files.
- **Metadata (`blueprint.yaml`):**
  ```yaml
  name: basic-vm
  description: A simple Ubuntu VM on Proxmox
  version: 1.0.0
  inputs:
    - name: vm_name               # required — no default
    - name: cores                 # optional — has default
      default: 2
  resources:
    - vm.yaml
  ```

## The `inputs:` Schema

A blueprint declares every template variable it reads in an `inputs:` list.
Presence of a `default:` determines whether the input is **optional** (the
default supplies the value if the package omits it) or **required** (the
package must supply it; otherwise template rendering fails).

```yaml
inputs:
  # Required per-instance input — package must provide this value.
  - name: vm_name
    description: "Hostname and Proxmox VM name"

  # Optional input — falls back to the declared default.
  - name: cores
    description: "Virtual CPU count"
    type: integer
    default: 2
```

**Entry keys** (all optional except `name`):

| Key           | Purpose                                                            |
| :------------ | :----------------------------------------------------------------- |
| `name`        | Variable name (required, unique within the scope).                 |
| `description` | Human-readable help text shown in tooling and `config doctor`.     |
| `type`        | Declared type hint. Informational; not enforced by the validator.  |
| `default`     | Default value. Presence marks the input as optional.               |

Unknown keys are rejected at resolve time to catch typos early. Declaring
both `inputs:` and the legacy `defaults:` section in the same scope is a
hard error — `inputs:` is the single variable-declaration mechanism.

### Per-Provider Inputs

Multi-provider blueprints (those with a top-level `providers:` block) may
declare inputs at two levels:

- **Top-level `inputs:`** — always in scope. Values here must be supplied by
  every package that instantiates the blueprint, regardless of provider.
- **Per-provider `inputs:`** — only in scope when that provider's templates
  are rendered. Use this for values that only make sense for one provider
  (e.g. `server_vmid` is proxmox-only; `ssh_public_key` is OCI-only).

```yaml
name: k3s-cluster
inputs:
  - name: cluster_name
    default: k3s-cluster       # shared, optional
providers:
  proxmox:
    inputs:
      - name: server_vmid      # proxmox-only, required
      - name: cores
        default: 2             # proxmox-only, optional
    resources:
      - providers/proxmox/vm.yaml
  oci:
    inputs:
      - name: image            # oci-only, required
      - name: ssh_public_key   # oci-only, required
    resources:
      - providers/oci/instance.yaml
```

### Migration (Before / After)

**Before** — legacy `defaults:` only:

```yaml
defaults:
  cores: 2
  memory: 4096
# vm_name is referenced by vm.yaml but never declared,
# so `config doctor --deep` flags it as an undefined variable.
```

**After** — unified `inputs:`:

```yaml
inputs:
  - name: vm_name              # now declared as required
  - name: cores
    default: 2
  - name: memory
    default: 4096
```

## Validation and Checks

- After creation, run `foundry infra doctor --env <env>` within the generated repo to ensure configs are sound.

## Examples

- **Instantiate a VM blueprint:**
  ```bash
  foundry config new create basic-vm ./my-new-vm
  ```
- **Example structure:**
  ```
  basic-vm/
  ├── blueprint.yaml
  ├── vm.yaml
  └── README.md
  ```

## Related Documentation

- [InfraFoundry CLI Reference](../usage/cli-reference.md)
- [Configuration Guide](overview.md)
- [YAML-Only Configuration](yaml-only-config.md)

## Troubleshooting

- **Symptom:** Blueprint not found. **Fix:** Verify the blueprint name matches a directory under `src/infrafoundry/blueprints/`; verify custom blueprints are placed in the expected directory.
- **Symptom:** Generated files missing. **Fix:** Ensure `blueprint.yaml` lists files if selective inclusion is used; otherwise include all files in the blueprint directory.

---

Last updated: 2026-04-14


---
[Back to Table of Contents](../index.md)
