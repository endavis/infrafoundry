# Policy Configuration Guide

InfraFoundry includes a pluggable policy engine that allows you to enforce rules on your infrastructure before deployment. Policies can block deployments (ERROR) or just warn users (WARNING).

## Configuration Location

Policies are defined in YAML files located in the `policies/` directory of your configuration repository. You can organize them into multiple files (e.g., `naming.yaml`, `security.yaml`).

**Example Path:** `my-config-repo/policies/default.yaml`

## Policy Structure

Each policy file contains a root `policies` list. Each policy entry supports the following fields:

```yaml
policies:
  - name: unique-policy-id       # Required: Unique identifier
    description: "Human readable" # Optional: Description of the rule
    type: policy_type_name       # Required: One of the supported types (see below)
    level: error                 # Optional: 'error' (block) or 'warning' (default: warning)
    enabled: true                # Optional: Enable/disable policy (default: true)
    environments:                # Optional: List of envs this applies to. If omitted, applies to all.
      - prod
    rules:                       # Required: Configuration specific to the policy type
      key: value
```

## Supported Policy Types

### 1. Resource Limits (`resource_limit`)

Enforce limits on compute resources (CPU, Memory) for VMs and containers.

**Rules Schema:**
- `limits`:
    - `max_cpu`: (int) Maximum cores allowed.
    - `max_memory_mb`: (int) Maximum RAM in MB.

**Example:**
```yaml
  - name: prod-limits
    type: resource_limit
    level: error
    environments: [prod]
    rules:
      limits:
        max_cpu: 16
        max_memory_mb: 32768
```

### 2. Naming Conventions (`naming_convention`)

Enforce regex patterns for resource names. You can define a global pattern and specific patterns per provider/type.

**Rules Schema:**
- `patterns`: Map of "selector" to "regex".
    - `*`: Matches all resources.
    - `provider:type`: Matches specific resources (e.g., `proxmox:vm`).

**Example:**
```yaml
  - name: strict-naming
    type: naming_convention
    rules:
      patterns:
        # Must be kebab-case
        "*": "^[a-z0-9]+(-[a-z0-9]+)*$"
        # VMs must start with role
        "proxmox:vm": "^(web|db|app)-.*$"
```

### 3. Required Tags (`required_tags`)

Ensure specific tags are present on resources (supported providers only, e.g., Proxmox).

**Rules Schema:**
- `tags`: List of required tag strings.

**Example:**
```yaml
  - name: audit-tags
    type: required_tags
    level: warning
    rules:
      tags:
        - managed-by-infrafoundry
        - cost-center-required
```

### 4. Allowed Providers (`allowed_providers`)

Restrict which providers can be used in specific environments.

**Rules Schema:**
- `allowed`: List of allowed provider names.

**Example:**
```yaml
  - name: no-k8s-in-dev
    type: allowed_providers
    level: error
    environments: [dev]
    rules:
      allowed:
        - proxmox
        - opnsense
```

## Usage

Run policy checks via the CLI:

```bash
# Check without blocking (reports violations)
infra policies check --env dev

# Enforce policies (exit code 1 if ERROR level violations found)
infra policies check --env dev --enforce
```
