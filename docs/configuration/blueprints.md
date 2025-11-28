# Configuration Blueprints Guide

InfraFoundry supports creating new infrastructure projects from templates called "Blueprints". This allows teams to standardize their configuration patterns and get started quickly with best practices.

## Usage

Use the `infra new` command to interact with blueprints:

```bash
# List available blueprints
infra new list

# Instantiate a blueprint
infra new create <blueprint-name> <target-directory>
```

Example:
```bash
# Create a new project from the 'basic-vm' blueprint
infra new create basic-vm ./my-new-vm
```

## Creating Blueprints

A blueprint is simply a directory containing a metadata file and template files.

### Directory Structure

Blueprints can be stored in:
1. The built-in `src/infrafoundry/blueprints/` directory (for core blueprints).
2. (Future) An external blueprints repository configured via settings.

Example structure for `basic-vm`:
```
basic-vm/
├── blueprint.yaml    # Metadata
├── vm.yaml           # Configuration template
└── README.md         # Instructions (optional)
```

### blueprint.yaml

This required file defines the blueprint's metadata:

```yaml
name: basic-vm
description: A simple Ubuntu VM on Proxmox
version: 1.0.0
author: InfraFoundry Team
# Optional: explicitly list files to include (defaults to all files in dir)
# files:
#   vm.yaml: "vms:\n  ..."
```

### Template Files

All other files in the directory are copied as-is to the target directory when the blueprint is instantiated. In future versions, these will support Jinja2 templating for dynamic variable substitution.

**vm.yaml example:**
```yaml
vms:
  - name: ubuntu-vm-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 4096
    disk:
      size: 32G
      storage: local-lvm
    network:
      bridge: vmbr0
      tag: 100
    ipconfig: ip=dhcp
    onboot: true
    tags:
      - basic
```
