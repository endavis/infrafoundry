# Infrastructure Packages

## Overview

Infrastructure packages are self-contained directories within a provider that bundle
resource templates, variables, and event handlers into a single deployable unit.
Instead of scattering configuration across `settings.yaml`, provider resource files,
and scripts directories, a package keeps everything together.

## Directory Structure

A package is a subdirectory of a provider directory containing an `infrafoundry.yml`
manifest file:

```
envs/dev/
  settings.yaml
  proxmox/
    vm.yaml                    # Regular provider resources
    ontap-cluster/             # Infrastructure package
      infrafoundry.yml         # Package manifest
      vm.yaml                  # Resource template (Jinja2)
      network.yaml             # Resource template (Jinja2)
      scripts/
        cluster-setup.sh       # Event handler script
      roles/
        ontap-config/          # Ansible role (excluded from scanning)
```

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

Packages are discovered automatically during resource loading:

1. Only **direct subdirectories** of provider directories are scanned (no recursion)
2. A subdirectory is a package if it contains `infrafoundry.yml`
3. The following directory names are **excluded** from scanning:
   `roles`, `tasks`, `handlers`, `defaults`, `vars`, `meta`, `files`, `templates`, `scripts`
4. Packages are loaded in alphabetical order by directory name

## Loading Order

Package resources are loaded after regular provider resources. Package events
are registered with the event bus after all resources (from all providers) have
been loaded. This means:

1. Regular resources from `*.yaml` files in provider directories
2. Package resources from subdirectories with `infrafoundry.yml`
3. Resource-centric resources from `resources/*.yaml`
4. Package events registered with the event bus

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
