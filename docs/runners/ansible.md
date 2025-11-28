# Ansible Runner Guide

InfraFoundry integrates Ansible for post-deployment configuration management. This runner allows you to apply Ansible roles and tasks to resources provisioned by Terraform.

For an overview of how runners interact and their fixed execution order, please refer to the [Runner Execution Overview](overview.md).

## Overview

The Ansible runner automatically:
1. Generates an Ansible inventory from your resource state (Terraform outputs).
2. Generates a `playbook.yml` applying your configured roles and tasks.
3. Executes `ansible-playbook` against the provisioned infrastructure.

## Configuration

Configuration is done per-resource in your YAML files.

### 1. Inline Tasks (`ansible_tasks`)

For simple, one-off configurations specific to a resource.

```yaml
vms:
  - name: web-server-01
    # ... VM config ...
    ansible_tasks:
      - name: Install Nginx
        module: apt
        params:
          name: nginx
          state: present
          update_cache: yes
```

### 2. Reusable Roles (`ansible_roles`)

For complex, reusable configuration logic. This is the preferred method for standard services.

#### Directory Structure
Place your roles in a `roles/` directory in your configuration repository:

```text
config-repo/
├── envs/
│   └── dev/
│       └── ...
└── roles/
    ├── common/
    │   └── tasks/
    │       └── main.yml
    └── webserver/
        ├── tasks/
        │   └── main.yml
        └── templates/
            └── nginx.conf.j2
```

#### Usage in YAML

```yaml
vms:
  - name: app-server
    ansible_roles:
      - common
      - webserver
    ansible_vars:
      webserver_port: 8080
      upstream_servers:
        - 10.0.0.5
        - 10.0.0.6
```

## Variables

Variables can be passed directly to Ansible via `ansible_vars`. These are available in your tasks and templates.

```yaml
vms:
  - name: db-server
    ansible_vars:
      db_name: production
      max_connections: 100
```

Sensitive variables should be managed via SOPS secrets in your environment configuration, which are passed securely to Ansible.

## Execution

The Ansible runner executes automatically during `infra apply` if Ansible configurations are present.

```bash
# Plan includes Ansible dry-run (check mode)
infra plan --env dev

# Apply executes the playbook
infra apply --env dev
```