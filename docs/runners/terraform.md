# Terraform Runner Guide

InfraFoundry uses Terraform as its core provisioning engine. While you configure your infrastructure using simplified YAML, InfraFoundry generates, validates, and executes standard Terraform code behind the scenes.

## Overview

The Terraform runner:
1. **Generates**: Converts your YAML resource definitions into `.tf` files using Jinja2 templates.
2. **Configures**: Maps environment settings and secrets into `terraform.tfvars`.
3. **Executes**: Runs `terraform init`, `plan`, and `apply` to manage the resource lifecycle.
4. **Tracks**: Captures resource IDs (like VM IDs) to map them to your configuration.

## Configuration

You do not write Terraform HCL directly. Instead, you define resources in YAML, and providers map them to Terraform resources.

### Resource Definition

```yaml
vms:
  - name: db-prod-01
    node: pve01
    cores: 4
    memory: 16384
    ipconfig: ip=10.0.0.5/24,gw=10.0.0.1
```

This is automatically compiled into a Terraform resource block (e.g., `proxmox_vm_qemu`).

### Settings & Secrets

Global settings (like API URLs) and secrets are defined in your environment's `settings.yaml` and passed to Terraform as variables.

```yaml
# settings.yaml
provider_settings:
  proxmox:
    api_url: https://pve.example.com:8006
    storage: local-zfs
```

This generates a `terraform.tfvars` file in the output directory.

## Customization

InfraFoundry is designed to abstract Terraform complexity. However, you can influence the generated Terraform through specific provider features:

*   **Cloud-Init Snippets**: Some providers (like Proxmox) allow injecting raw cloud-init user data via snippet files referenced in your YAML.
*   **Provider Options**: Advanced options in `settings.yaml` often map directly to Terraform provider configuration blocks.

*Note: Direct injection of raw HCL snippets is generally not supported to ensure state consistency and validity.*

## State Management

InfraFoundry manages the Terraform state file (`terraform.tfstate`) for you.

*   **Location**: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`
*   **Persistence**: InfraFoundry ensures this state is preserved across runs.
*   **Backends**: By default, local state is used. Remote backends (S3, Postgres, etc.) can be configured via environment variables or settings if supported by the provider plugin.

## Execution

Terraform runs automatically during the plan and apply phases.

```bash
# Plan: Generates .tf files and runs 'terraform plan'
infra plan --env dev

# Apply: Runs 'terraform apply -auto-approve'
infra apply --env dev
```

## Debugging

If a Terraform error occurs, `infra` will display the output. You can inspect the generated files to debug issues:

```bash
# Inspect generated configuration
cat generated/dev/terraform/proxmox/main.tf
cat generated/dev/terraform/proxmox/terraform.tfvars
```

You can also manually run terraform commands in the generated directory for debugging:

```bash
cd generated/dev/terraform/proxmox/
terraform plan
```
