---
title: "Configuration Blueprints Guide"
description: "Use blueprints to scaffold configuration repositories and services"
audience:
  - users
tags:
  - configuration
---

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

## The `requirements:` Block

A blueprint declares the Python packages and Ansible collections its event handlers
and playbooks need. InfraFoundry checks them before any provider work, so a missing
dependency fails the run up front instead of after infrastructure has been created
([ADR-0017](../decisions/0017-blueprint-declared-requirements-with-a-preflight-check.md)).

```yaml
requirements:
  python:
    - spec: "netapp-lib>=2021.6.25"   # PEP 508 requirement
      import: netapp_lib              # optional: module to import-check
    - "requests>=2.31"                # a plain string works when no import name is needed
  ansible_collections: requirements.yml   # ansible-galaxy requirements file, relative to the blueprint
```

- **`python`**: each entry is a PEP 508 spec, as a string or as a mapping with `spec` and an
  optional `import`. Use `import` when the module name differs from the distribution name.
  An entry whose environment marker excludes this interpreter is skipped.
- **`ansible_collections`**: a path, inside the blueprint directory, to the `requirements.yml`
  you would pass to `ansible-galaxy collection install -r`. Collection versions use galaxy's
  syntax (`*`, `1.2.3`, `>=22.0.0`, `>=1.0,<2.0`).
- The block is optional. A blueprint without it has no requirements.

**When it is checked.** `foundry infra plan`, `infra apply` and `infra destroy` check the
requirements of every blueprint used by the packages in scope. That is the whole environment,
narrowed by `--package` or `--provider`. An unmet requirement stops the run with error
`IF-PACKAGE-002`, which names the package, the blueprints that need it, and the command that
installs it. `foundry config doctor` reports the same check for every environment.

**Install them yourself.** Nothing is installed during a run. Install Python packages into the
environment that runs InfraFoundry (`uv pip install '<spec>'`) and collections with
`ansible-galaxy collection install -r <file>`.

!!! note "Which Python Ansible uses"
    The check looks at the interpreter running InfraFoundry. Ansible runs local-connection
    modules under the interpreter it discovers, which may be the system Python, unless the
    inventory sets `ansible_python_interpreter: "{{ ansible_playbook_python }}"`. Pin it in
    blueprints whose modules need these packages.

## Shared Resource Templates

Multi-provider blueprints can use a single shared resource file with Jinja2
provider conditionals instead of maintaining separate files per provider. The
`provider` variable is automatically injected into the template rendering
context, giving templates access to the effective provider name.

### Pattern

Use the resource-centric format (`resources:` key) in shared files so each
provider block can declare its own resource type:

```yaml
# shared.yaml — one file, multiple providers (resource-centric format)
resources:
{% if provider == "proxmox" %}
  - provider: proxmox
    type: vm
    name: {{ vm_name }}-node
    config:
      cores: {{ cores }}
      memory: {{ memory_gb | to_mib }}
{% elif provider == "oci" %}
  - provider: oci
    type: instance
    name: {{ vm_name }}-node
    config:
      shape: VM.Standard.E4.Flex
      ocpus: {{ cores }}
      memory_in_gbs: {{ memory_gb }}
{% endif %}
```

Reference the shared file from both provider blocks in `blueprint.yaml`:

```yaml
name: k3s-cluster
defaults:
  vm_name: k3s
  cores: 2
  memory_gb: 8
providers:
  proxmox:
    resources:
      - shared.yaml
  oci:
    resources:
      - shared.yaml
```

### Guidance

- **Use shared files** when the resource count is small and the conditional
  logic is simple (a few `{% if %}`/`{% elif %}` blocks).
- **Use separate per-provider files** when schemas differ significantly or
  the template would become hard to read. This is the recommended default
  for most multi-provider blueprints.
- The `provider` variable is also available in event handler templates and
  in non-blueprint packages.
- If a user-defined variable named `provider` already exists in the
  manifest's `variables`, the user value takes precedence over the
  injected value.

## Optional Resources (File-Level Gating)

A blueprint resource file may conditionally emit nothing when an input is
unset, so packages that don't need the resource produce no output instead of
carrying an empty placeholder. Wrap the file's `resources:` block in a
top-level Jinja2 `{% if %}` and provide an explicit `resources: []` in the
`{% else %}` branch so the file always yields a valid resource-centric
document.

```yaml
{% if nfs_server %}
resources:
  - provider: proxmox
    type: storage
    name: "{{ vm_name }}-nfs"
    config:
      backend: nfs
      server: "{{ nfs_server }}"
      export: "{{ nfs_export }}"
{% else %}
resources: []
{% endif %}
```

This pattern pairs naturally with an optional input that defaults to an empty
string or list. Declare the gating input in `inputs:` and leave the default
empty so packages that don't need the resource can stay silent:

```yaml
inputs:
  - name: nfs_server
    description: "NFS server address. Empty: no NFS storage resource is created."
    default: ""
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
