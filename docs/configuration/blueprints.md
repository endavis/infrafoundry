# Configuration Blueprints Guide

## Overview

Blueprints are template projects that scaffold new InfraFoundry configuration repositories or services with best practices baked in.

## Audience and Prerequisites

- **Audience:** Operators and platform teams standardizing configuration patterns.
- **Prereqs:** InfraFoundry installed (`uv run infra`), access to built-in or custom blueprints, and a target directory to create into.

## When to Use This

- Bootstrapping a new config repo or service quickly.
- Enforcing consistent structure across teams/tenants.
- Sharing common patterns for VMs, networks, or multi-provider stacks.

## Quick Start

```bash
infra new list
infra new create basic-vm ./my-new-vm
```

## Configuration Details

- **Command:** `infra new create <blueprint-name> <target-directory>`.
- **Built-in location:** `src/infrafoundry/blueprints/`.
- **Blueprint contents:** `blueprint.yaml` metadata + template files (copied as-is). Future versions may add Jinja2 templating.
- **Metadata (`blueprint.yaml`):**
  ```yaml
  name: basic-vm
  description: A simple Ubuntu VM on Proxmox
  version: 1.0.0
  author: InfraFoundry Team
  # Optional: files section to control included files
  # files:
  #   vm.yaml: "vms:\n  ..."
  ```

## Validation and Checks

- List available blueprints to confirm discovery: `infra new list`.
- After creation, run `infra validate --env <env>` within the generated repo to ensure configs are sound.

## Examples

- **Instantiate a VM blueprint:**
  ```bash
  infra new create basic-vm ./my-new-vm
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

- **Symptom:** Blueprint not found. **Fix:** Check name from `infra new list`; verify custom blueprints are placed in the expected directory.
- **Symptom:** Generated files missing. **Fix:** Ensure `blueprint.yaml` lists files if selective inclusion is used; otherwise include all files in the blueprint directory.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
