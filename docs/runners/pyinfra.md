# PyInfra Runner Guide

## Overview

The PyInfra runner executes Python-based deploys for post-provision configuration. InfraFoundry generates inventory and deploy files from your YAML definitions and runs `pyinfra` over SSH.

## Audience and Prerequisites

- **Audience:** Operators preferring Python-based automation for configuration and app deploys.
- **Prereqs:** PyInfra installed, SSH access to provisioned hosts, and optional reusable deploy modules in `pyinfra/`.

## When to Use This

- Application deployment or configuration logic best expressed in Python.
- Faster/lighter alternative to Ansible for some workflows.
- Combining inline operations with reusable deploy functions.

## Quick Start

1. Add PyInfra fields to a resource:
   ```yaml
   resources:
     - provider: proxmox
       type: vm
       name: web-node-01
       config:
         pyinfra_ops:
           - name: Install Nginx
             operation: apt.packages
             params:
               packages: ["nginx"]
               update: true
               _sudo: true
   ```
2. Apply:
   ```bash
   foundry infra apply --env dev
   ```
   Inventory and deploy scripts are generated under `generated/{env}/pyinfra/{provider}/` and executed.

## Configuration Details

- **Inline operations:** `pyinfra_ops` map to `pyinfra.operations` with `name`, `operation`, `params`.
- **Reusable deploy functions:** `pyinfra_deploy_funcs` reference dotted functions from `pyinfra/` modules in the config repo (e.g., `web.setup_nginx`).
- **Inventory:** Generated from resource state; groups and connection data are auto-populated.
- **Execution order:** Runs after Terraform (and after Ansible if it shares the same priority/registration order) per runner priorities.

## Validation and Checks

- Validate configs: `foundry infra doctor --env <env>`.
- Ensure SSH connectivity and credentials from `settings.yaml`/`provider_ssh`.
- Optionally dry-run via `foundry infra plan --env <env>` to see generation without execution.

## Examples

- **Deploy function module (`pyinfra/web.py`):**
  ```python
  from pyinfra.operations import apt, systemd

  def setup_nginx():
      apt.packages(name="Install Nginx", packages=["nginx"], update=True, _sudo=True)
      systemd.service(name="Restart Nginx", service="nginx", running=True, enabled=True, _sudo=True)
  ```
- **Use deploy function in YAML:**
  ```yaml
  pyinfra_deploy_funcs:
    - web.setup_nginx
  ```

## Related Documentation

- [Runner Execution Overview](overview.md)
- [SSH Authentication](../guides/ssh-authentication.md)
- [Configuration Guide](../configuration/overview.md)
- [Pluggable Runner System](../architecture/pluggable-runners.md)

## Troubleshooting

- **Symptom:** Operations not executed. **Fix:** Ensure `pyinfra_ops` or `pyinfra_deploy_funcs` are present; check generated PyInfra files.
- **Symptom:** SSH connection issues. **Fix:** Verify SSH settings and host reachability; align with runner priorities if bootstrapping Python is needed.
- **Symptom:** Module not found. **Fix:** Place modules under `pyinfra/` in the config repo and reference with dotted paths.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
