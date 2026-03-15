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

## Resource-Level Events

Resources can declare lifecycle event handlers directly in their definition.
Unlike package-level events (which fire on runner lifecycle), resource-level
events fire based on **what actually happened** to the resource during apply:

| Event Key | Fires When |
|:----------|:-----------|
| `on_create` | Resource was newly created (terraform `+ create`) |
| `on_update` | Resource was modified in place (terraform `~ update`) |
| `on_destroy` | Resource is being destroyed (terraform `- destroy`) |

### Declaring events on a resource

Add an `events` key to a resource definition inside a package resource template:

```yaml
vm:
  - name: {{ cluster_name }}-node1
    cores: 4
    memory: 16384
    events:
      on_create:
        - type: script
          name: serial-setup
          script: scripts/ontap-serial-setup.sh
          timeout: 600
      on_destroy:
        - type: script
          name: cleanup
          script: scripts/ontap-cleanup.sh
```

Or in a resource-centric YAML file:

```yaml
resources:
  - provider: proxmox
    type: vm
    name: ontapcl-01
    config:
      vmid: 220
      target_node: pve1
    events:
      on_create:
        - type: ansible
          name: configure-node
          playbook: playbooks/configure.yml
          timeout: 300
```

### Handler types

Resource-level events support the same handler types as package-level events,
plus a new `ansible` handler type:

| Type | Description |
|:-----|:-----------|
| `script` | Run a shell script |
| `webhook` | Send an HTTP webhook |
| `python` | Call a Python callable |
| `ansible` | Run an Ansible playbook |

### Ansible handler configuration

The `ansible` handler runs an Ansible playbook as an event handler:

```yaml
events:
  on_create:
    - type: ansible
      name: configure-node
      playbook: playbooks/configure.yml
      inventory: inventory/hosts.yml    # optional
      extra_vars:                        # optional
        target_host: "{{ resource_name }}"
      timeout: 300
      continue_on_error: false
```

| Field | Type | Required | Description |
|:------|:-----|:---------|:-----------|
| `playbook` | string | Yes | Path to playbook (relative to environment directory) |
| `inventory` | string | No | Inventory file path (relative to environment directory) |
| `extra_vars` | dict | No | Extra variables passed via `--extra-vars` |
| `timeout` | int | No | Max execution time in seconds (default: 300, max: 3600) |
| `continue_on_error` | bool | No | Don't abort on failure (default: false) |

### Script path rewriting

Script and playbook paths in resource-level events are rewritten the same way
as package-level event paths. A path like `scripts/setup.sh` in a package at
`envs/dev/proxmox/ontap-cluster/` becomes
`proxmox/ontap-cluster/scripts/setup.sh`.

### Why resource-level events?

- **Idempotent:** Handlers only fire when the resource outcome matches (e.g.,
  `on_create` only fires on first creation, not every apply)
- **No blocking:** Eliminates the problem where `RUNNER_COMPLETED` handlers
  block subsequent providers
- **Self-contained:** The resource carries its config, provider, and lifecycle
  events -- no cross-referencing by name
- **Portable:** Move or rename a resource and its events move with it

### Deprecation of runner lifecycle events

The `RUNNER_STARTING` and `RUNNER_COMPLETED` events are deprecated in favor of
resource-level events. They continue to work but emit `DeprecationWarning`
messages. Migrate to resource-level `on_create`, `on_update`, and `on_destroy`
events for new configurations.

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
