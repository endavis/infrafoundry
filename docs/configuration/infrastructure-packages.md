# Infrastructure Packages

## Overview

Infrastructure packages are self-contained directories that bundle resource templates,
variables, and event handlers into a single deployable unit. Instead of scattering
configuration across `settings.yaml`, provider resource files, and scripts directories,
a package keeps everything together.

Packages can be placed in two locations:

- **Provider-scoped:** Under a provider directory (`envs/{env}/{provider}/{package}/`)
- **Env-root:** Directly under the environment directory (`envs/{env}/{package}/`)

## Directory Structure

### Provider-scoped packages

A provider-scoped package is a subdirectory of a provider directory containing an
`infrafoundry.yml` manifest file. The provider is inferred from the parent directory:

```
envs/dev/
  settings.yaml
  proxmox/
    vm.yaml                    # Regular provider resources (deprecated)
    ontap-cluster/             # Infrastructure package
      infrafoundry.yml         # Package manifest
      vm.yaml                  # Resource template (Jinja2)
      network.yaml             # Resource template (Jinja2)
      scripts/
        cluster-setup.sh       # Event handler script
      roles/
        ontap-config/          # Ansible role (excluded from scanning)
```

### Env-root packages

An env-root package sits directly under the environment directory rather than under
a provider. Because there is no parent provider directory to infer from, env-root
packages **must** declare a `provider` field in their manifest:

```
envs/dev/
  settings.yaml
  ontap-cluster/               # Env-root package
    infrafoundry.yml           # Must include provider field
    vm.yaml
    network.yaml
  proxmox/                     # Provider directory (no infrafoundry.yml)
    vm.yaml
```

Env-root packages are discovered during resource loading and are skipped by provider
discovery so they are not mistaken for provider directories.

## Package Manifest (`infrafoundry.yml`)

The manifest declares the package name, variables, resource templates, and event handlers.

```yaml
name: ontap-cluster
description: NetApp ONTAP cluster lab deployment

variables:
  cluster_name: lab-ontap
  node_count: 2
  mgmt_network: VLAN100
  data_network: VLAN200

resources:
  - vm.yaml
  - network.yaml

events:
  AFTER_APPLY:
    - type: script
      script: scripts/cluster-setup.sh
      timeout: 300
      resources:
        - lab-ontap-node1
        - lab-ontap-node2
```

Handlers with a `resources` list only fire when those resources are targeted by
the `-r` CLI filter. Omit `resources` to fire on every invocation. See the
[Resource-Scoped Event Handlers](../development/event-system.md#resource-scoped-event-handlers)
section for details.

### Fields

| Field | Type | Required | Description |
|:------|:-----|:---------|:------------|
| `name` | string | Yes | Package identifier |
| `description` | string | No | Human-readable description |
| `provider` | string | Env-root: Yes, Provider-scoped: No | Target provider name. Required for env-root packages; optional override for provider-scoped packages. |
| `variables` | dict | No | Key-value pairs for template rendering |
| `resources` | list[string] | No | Resource template files to render and load |
| `events` | dict | No | Event handlers (same format as `settings.yaml` events) |

## Resource Templates

Resource files listed in `resources` are Jinja2 templates rendered with the manifest's
`variables` before being parsed as YAML. This means users only edit `infrafoundry.yml`
to configure the package.

### Example Template (`vm.yaml`)

```yaml
vm:
  - name: {{ cluster_name }}-node1
    cores: 4
    memory: 16384
    network:
      - bridge: {{ mgmt_network }}
      - bridge: {{ data_network }}

  - name: {{ cluster_name }}-node2
    cores: 4
    memory: 16384
    network:
      - bridge: {{ mgmt_network }}
      - bridge: {{ data_network }}
```

With the manifest variables above, this renders to:

```yaml
vm:
  - name: lab-ontap-node1
    cores: 4
    memory: 16384
    network:
      - bridge: VLAN100
      - bridge: VLAN200
  - name: lab-ontap-node2
    # ...
```

### Template Rules

- Templates use [Jinja2](https://jinja.palletsprojects.com/) syntax
- **StrictUndefined** is enforced: referencing an undefined variable raises an error
- After rendering, the result must be valid YAML
- Resource type is derived from the filename (same as regular provider resources)
- Both singular (`vm`) and plural (`vms`) keys are supported

## Package Events

Events declared in the manifest follow the same format as
[environment events](../development/event-system.md) in `settings.yaml`.
The key difference is that **script paths are automatically rewritten**
to be relative to the environment directory.

For example, if a package at `envs/dev/proxmox/ontap-cluster/` declares:

```yaml
events:
  AFTER_APPLY:
    - type: script
      script: scripts/cluster-setup.sh
```

The script path is rewritten to `proxmox/ontap-cluster/scripts/cluster-setup.sh`,
which ScriptHandler resolves as `envs/dev/proxmox/ontap-cluster/scripts/cluster-setup.sh`.

Non-script handlers (webhook, python) are passed through unchanged.

## Package Discovery

Packages are discovered automatically during resource loading from two locations:

### Provider-scoped discovery

1. Only **direct subdirectories** of provider directories are scanned (no recursion)
2. A subdirectory is a package if it contains `infrafoundry.yml`
3. The following directory names are **excluded** from scanning:
   `roles`, `tasks`, `handlers`, `defaults`, `vars`, `meta`, `files`, `templates`, `scripts`
4. Packages are loaded in alphabetical order by directory name

### Env-root discovery

1. Direct subdirectories of `envs/{env}/` are scanned for `infrafoundry.yml`
2. Directories named `resources` or `secrets` are excluded, along with the standard
   exclusion list above
3. Directories containing `infrafoundry.yml` are **skipped** during provider discovery
   so they are not mistaken for provider directories
4. Env-root packages must declare a `provider` field in the manifest

## Per-Package State Isolation

Each package gets its own terraform working directory and state file. When a
package context is active, generated terraform files are written to
`generated/{env}/terraform/{package-name}/` instead of the default
`generated/{env}/terraform/{provider}/`.

This means:

- **Independent state:** Applying or destroying one package cannot affect
  another package's terraform state.
- **Targeted operations:** `plan`, `apply`, and `destroy` process each package
  separately, running `terraform init`, `plan`, and `apply` within the
  package-scoped directory.
- **Loose resources** (not inside a package) continue to use the per-provider
  directory `generated/{env}/terraform/{provider}/`.

### Directory layout example

```
generated/prod/
  terraform/
    ontap-cluster/           # Package-scoped state
      main.tf
      .terraform/
        terraform.tfstate
    k8s-cluster/             # Another package
      main.tf
      .terraform/
        terraform.tfstate
    proxmox/                 # Loose resources (per-provider)
      main.tf
      .terraform/
        terraform.tfstate
```

## Targeting Packages from the CLI

Use the `--package` / `-p` flag on `plan`, `apply`, and `destroy` to target all
resources in a specific package:

```bash
# Plan only the ontap-cluster package
infra plan --env prod --package ontap-cluster

# Apply a package (short flag)
infra apply --env prod -p ontap-cluster --auto-approve

# Destroy a package
infra destroy --env prod -p ontap-cluster
```

The `--package` flag resolves the package name to the list of resource names
declared in its manifest and passes them as a resource filter to the orchestrator.

!!! note
    `--package` (`-p`) and `--resource` (`-r`) are mutually exclusive. Use one
    or the other, not both.

## Loose Resource Deprecation

!!! warning "Deprecated"
    Loose resource files (YAML files not inside a package directory) are deprecated.
    They will continue to work but emit `DeprecationWarning` messages. Migrate them
    to packages with an `infrafoundry.yml` manifest.

## Loading Order

Package resources are loaded after regular provider resources. Package events
are registered with the event bus after all resources (from all providers) have
been loaded. This means:

1. Regular resources from `*.yaml` files in provider directories
2. Provider-scoped package resources from subdirectories with `infrafoundry.yml`
3. Env-root package resources from `envs/{env}/{package}/infrafoundry.yml`
4. Resource-centric resources from `resources/*.yaml`
5. Package events registered with the event bus

## Duplicate Detection

Resource names must be unique within a provider. If a package resource has the
same name as a regular resource or another package's resource, a `ValueError`
is raised during `get_all_resources_all_providers()`.

## Full Example

```
envs/dev/
  settings.yaml
  proxmox/
    ontap-cluster/
      infrafoundry.yml
      vm.yaml
      scripts/
        cluster-setup.sh
        cluster-teardown.sh
      roles/
        ontap-config/
          tasks/
            main.yml
```

**`infrafoundry.yml`:**
```yaml
name: ontap-cluster
description: NetApp ONTAP cluster for lab environment

variables:
  cluster_name: lab-ontap
  node_count: 2
  mgmt_network: VLAN100

resources:
  - vm.yaml

events:
  AFTER_APPLY:
    - type: script
      script: scripts/cluster-setup.sh
      timeout: 300
  BEFORE_DESTROY:
    - type: script
      script: scripts/cluster-teardown.sh
```

**`vm.yaml`:**
```yaml
vm:
  - name: {{ cluster_name }}-node1
    cores: 4
    memory: 16384
    network:
      - bridge: {{ mgmt_network }}
  - name: {{ cluster_name }}-node2
    cores: 4
    memory: 16384
    network:
      - bridge: {{ mgmt_network }}
```
