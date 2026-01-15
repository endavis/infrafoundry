# Pulumi Runner Guide

## Overview

The Pulumi runner provisions infrastructure from YAML by generating Pulumi programs, managing stacks, and executing `pulumi preview/up/destroy`. This is an experimental runner demonstrating InfraFoundry's pluggable runner architecture.

## Audience and Prerequisites

- **Audience:** Operators and developers experimenting with Pulumi as an alternative infrastructure tool.
- **Prereqs:** Pulumi installed, `INFRA_ENABLE_EXPERIMENTAL=1` environment variable set, config repo available, provider credentials configured.

## When to Use This

- Experimenting with Pulumi as an alternative to Terraform
- Testing the pluggable runner system
- Provisioning infrastructure with Pulumi's multi-language support
- Leveraging Pulumi's state management and policy capabilities

## Quick Start

```bash
# Enable experimental features
export INFRA_ENABLE_EXPERIMENTAL=1

# Run standard workflows
infra plan --env dev
infra apply --env dev
```

## Configuration Details

- **Experimental Status:** Pulumi runner is experimental and requires `INFRA_ENABLE_EXPERIMENTAL=1` to enable.
- **Resource definitions:** YAML resources map to Pulumi program resources; the provider generates Pulumi code.
- **Stack management:** Pulumi stacks are initialized/selected automatically based on environment name.
- **State location:** Managed by Pulumi in `generated/{env}/pulumi/{provider}/.pulumi/` or configured Pulumi backend.
- **Program files:** Generated Pulumi programs in `generated/{env}/pulumi/{provider}/`.

## Protocol Support

The Pulumi runner implements all 5 runner protocols:

- **Plannable** - Generates execution plans via `pulumi preview`
- **Applyable** - Applies infrastructure changes via `pulumi up`
- **Destroyable** - Destroys infrastructure via `pulumi destroy`
- **StateAware** - Tracks resource URNs via `pulumi stack export`
- **DriftDetectable** - Detects configuration drift through preview output

This makes it functionally equivalent to TerraformRunner in terms of capabilities.

## Validation and Checks

- Validate configs before running:
  ```bash
  infra validate --env dev --check-api --check-refs
  ```
- Inspect generated files for debugging:
  ```bash
  ls generated/dev/pulumi/proxmox/
  cat generated/dev/pulumi/proxmox/Pulumi.yaml
  ```
- Check Pulumi installation:
  ```bash
  pulumi version
  ```

## Examples

- **Enable experimental features:**
  ```bash
  export INFRA_ENABLE_EXPERIMENTAL=1
  ```

- **YAML VM definition (maps to Pulumi resource):**
  ```yaml
  resources:
    - provider: proxmox
      type: vm
      name: db-prod-01
      config:
        node: pve01
        cores: 4
        memory: 16384
        ipconfig: ip=10.0.0.5/24,gw=10.0.0.1
  ```

- **Run Pulumi commands manually for debugging:**
  ```bash
  cd generated/dev/pulumi/proxmox
  pulumi preview
  pulumi up
  ```

- **Check stack state:**
  ```bash
  cd generated/dev/pulumi/proxmox
  pulumi stack ls
  pulumi stack export
  ```

## Pulumi Backend Configuration

Pulumi supports multiple backend options for state storage:

- **Local backend** (default): State stored in `.pulumi/` directory
- **Pulumi Cloud**: Configure via `pulumi login`
- **Self-managed backend**: S3, Azure Blob, GCS, etc.

Configure backend before running:
```bash
# Pulumi Cloud
pulumi login

# Self-managed S3 backend
pulumi login s3://my-pulumi-state-bucket
```

## Related Documentation

- [Runner Execution Overview](overview.md)
- [Pluggable Runner System](../architecture/pluggable-runners.md)
- [Implementing Runners](../development/implementing-runners.md)
- [Runner Protocol Quick Reference](../development/runner-protocol-quick-reference.md)
- [Configuration Guide](../configuration/overview.md)

## Troubleshooting

- **Symptom:** `PulumiRunner not found`. **Fix:** Ensure `INFRA_ENABLE_EXPERIMENTAL=1` is set in environment.
- **Symptom:** `pulumi command not found`. **Fix:** Install Pulumi from https://www.pulumi.com/docs/get-started/install/
- **Symptom:** Stack initialization fails. **Fix:** Ensure Pulumi backend is configured (`pulumi login`).
- **Symptom:** Pulumi errors on apply. **Fix:** Inspect generated Pulumi program; run `pulumi preview` manually in generated directory.
- **Symptom:** State conflicts. **Fix:** Configure Pulumi backend with proper state storage and ensure team members use same backend.
- **Symptom:** Missing credentials. **Fix:** Ensure `settings.yaml` contains provider credentials; configure Pulumi provider-specific credentials if needed.

## Known Limitations

- **Experimental**: This runner is under development and may have incomplete features
- **Limited testing**: Less battle-tested than Terraform/Ansible runners
- **Provider support**: Depends on provider implementation to generate Pulumi programs
- **Language support**: Currently generates Python Pulumi programs (extensible to other languages)

## Future Enhancements

Planned improvements for the Pulumi runner:

- Multi-language support (TypeScript, Go, C#, Java)
- Enhanced drift detection with detailed resource-level changes
- Pulumi Policy Pack integration
- Stack transformation and import capabilities
- Better error handling and output parsing

---

Last updated: 2025-12-23

---
[Back to Table of Contents](../index.md)
