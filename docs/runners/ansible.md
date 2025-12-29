# Ansible Runner Guide

## Overview

The Ansible runner configures provisioned resources by generating inventory and playbooks from your YAML definitions, then running `ansible-playbook`.

## Audience and Prerequisites

- **Audience:** Operators adding Ansible roles/tasks to InfraFoundry resources.
- **Prereqs:** Ansible installed, roles/tasks available in the config repo, and Terraform-provisioned resources with reachable SSH.

## When to Use This

- Post-provision configuration and service setup.
- Reusable roles across environments.
- Inline tasks for small, resource-specific changes.

## Quick Start

1. Add Ansible fields to a resource:
   ```yaml
   resources:
     - provider: proxmox
       type: vm
       name: web-01
       config:
         ansible_roles:
           - common
           - webserver
         ansible_vars:
           webserver_port: 8080
   ```
2. Run:
   ```bash
   infra apply --env dev
   ```
   Ansible inventory/playbook is generated and executed after provisioning.

## Configuration Details

- **Per-resource fields:** `ansible_roles`, `ansible_tasks`, `ansible_vars`.
- **Roles location:** `roles/` in the config repo (e.g., `roles/common`, `roles/webserver`).
- **Generated files:** Inventory/playbook under `generated/{env}/ansible/{provider}/`.
- **Execution order:** Runs after Terraform (see `runner_priorities`).

## Validation and Checks

- Validate configs: `infra validate --env <env> --check-api --check-refs`.
- Ensure SSH connectivity for hosts produced by Terraform.
- Use Ansible syntax/lint checks locally if needed.

## Examples

- **Inline task:**
  ```yaml
  ansible_tasks:
    - name: Install Nginx
      module: apt
      params:
        name: nginx
        state: present
        update_cache: yes
  ```
- **Roles with vars:**
  ```yaml
  ansible_roles:
    - common
    - webserver
  ansible_vars:
    webserver_port: 8080
    upstream_servers:
      - 10.0.0.5
      - 10.0.0.6
  ```

## Related Documentation

- [Runner Execution Overview](overview.md)
- [Configuration Guide](../configuration/overview.md)
- [SSH Authentication](../guides/ssh-authentication.md)
- [Pluggable Runner System](../architecture/pluggable-runners.md)

## Troubleshooting

- **Symptom:** Playbook not generated. **Fix:** Ensure resource includes Ansible fields; check `generated/{env}/ansible/{provider}`.
- **Symptom:** SSH fails. **Fix:** Verify SSH settings in `settings.yaml` and host reachability; confirm keys/ports.
- **Symptom:** Roles not found. **Fix:** Place roles under `roles/` in config repo and reference by directory name.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
