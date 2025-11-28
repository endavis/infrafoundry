# PyInfra Runner Guide

InfraFoundry supports [pyinfra](https://pyinfra.com/) as a pure-Python alternative to Ansible for configuration management. It offers faster execution and allows you to write deployment logic in standard Python.

For an overview of how runners interact and their fixed execution order, please refer to the [Runner Execution Overview](overview.md).

## Overview

The PyInfra runner:
1. Generates a `inventory.py` from your resource state.
2. Generates a `deploy.py` that orchestrates your configured operations.
3. Executes `pyinfra` over SSH.

## Configuration

You can define operations inline or point to reusable Python functions.

### 1. Inline Operations (`pyinfra_ops`)

For simple tasks, you can define operations directly in your YAML. This maps directly to `pyinfra.operations`.

```yaml
vms:
  - name: web-node-01
    # ... VM config ...
    pyinfra_ops:
      - name: Install Nginx
        operation: apt.packages
        params:
          packages: ["nginx"]
          update: true
          _sudo: true
      
      - name: Ensure Service Started
        operation: systemd.service
        params:
          service: "nginx"
          running: true
          enabled: true
          _sudo: true
```

### 2. Reusable Deploy Functions (`pyinfra_deploy_funcs`)

For complex logic, reusable components, or when you want to utilize the full power of Python, use custom deploy functions.

#### Directory Structure

Create a `pyinfra/` directory at the root of your configuration repository. InfraFoundry automatically copies this directory to the execution environment.

```text
config-repo/
├── envs/
│   └── dev/
│       └── ...
└── pyinfra/
    ├── __init__.py
    ├── web.py        <-- Your custom module
    └── database.py
```

#### Writing a Deploy Function

**`pyinfra/web.py`**:
```python
from pyinfra.operations import apt, server, systemd

def setup_nginx():
    """Install and configure Nginx."""
    apt.packages(
        name="Install Nginx",
        packages=["nginx"],
        update=True,
        _sudo=True,
    )
    
    systemd.service(
        name="Restart Nginx",
        service="nginx",
        running=True,
        enabled=True,
        _sudo=True,
    )
```

#### Usage in YAML

Reference the function using the dotted path `module.function`.

```yaml
vms:
  - name: web-cluster-01
    pyinfra_deploy_funcs:
      - web.setup_nginx
```

## Inventory Generation

InfraFoundry automatically generates the inventory based on the resources managed by the provider. 
- **Groups**: Resources are grouped by their snake_case name (e.g., `web_cluster_01`).
- **Connection Data**: IP addresses and SSH users are automatically populated from the infrastructure state.

## Execution

PyInfra runs automatically during the apply phase.

```bash
# Plan shows what would happen (dry-run)
infra plan --env dev

# Apply executes the changes
infra apply --env dev
```

## Best Practices

1. **Idempotency**: Ensure your Python functions are idempotent (safe to run multiple times). PyInfra operations are idempotent by default.
2. **Conditionals**: Use standard Python `if` statements in your deploy functions for logic that is hard to express in YAML.
3. **Secrets**: (Future) Access secrets injected into the environment variables or host data.
