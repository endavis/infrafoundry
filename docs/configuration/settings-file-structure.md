# Settings File Structure

## Overview

Each environment uses a single SOPS-encrypted `settings.yaml` to define metadata, SSH defaults, provider credentials, and overrides. InfraFoundry renders Terraform/Ansible inputs from this YAML—no HCL required.

## Audience and Prerequisites

- **Audience:** Config repo maintainers defining environment settings and secrets.
- **Prereqs:** Config repo with `envs/{env}`, `sops` + `age` installed, and provider credentials for targeted platforms.

## When to Use This

- Creating or updating environment settings and credentials.
- Adding provider-specific SSH overrides or defaults.
- Auditing the required fields for `settings.yaml`.

## Quick Start

1. Create `envs/{env}/settings.yaml` and add metadata, SSH, and provider settings.
2. Encrypt with SOPS/age:
   ```bash
   sops --encrypt --in-place envs/dev/settings.yaml
   ```
3. Validate and plan:
   ```bash
   infra validate --env dev --check-api
   infra plan --env dev
   ```

## Configuration Details

- **File location:** `envs/{env}/settings.yaml` (encrypted with SOPS/age).
- **Key sections:**
  - `name`, `description`, optional `variables` (for templates).
  - `providers` (list of provider names to enable for this environment).
  - `backend` (Terraform backend configuration for state management and locking).
  - `ssh` (global SSH defaults) and `provider_ssh` (per-provider overrides).
  - `provider_settings` per provider (credentials, endpoints, defaults).
- **Example structure:**
  ```yaml
  name: prod
  description: Production environment
  providers:
    - proxmox
    - opnsense
    - kubernetes
  variables:
    datacenter: dc1
    domain: example.com

  backend:
    type: s3
    s3:
      bucket: my-terraform-state
      key: prod/terraform.tfstate
      region: us-east-1
      dynamodb_table: terraform-locks
      encrypt: true

  ssh:
    user: automation
    key_path: /home/automation/.ssh/id_ed25519

  provider_ssh:
    proxmox:
      user: root
      key_path: /secure/keys/proxmox_ed25519
      port: 2222

  provider_settings:
    proxmox:
      api_url: https://pve01.example.com:8006
      api_token: pve-token-id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      node: pve01
      storage: local-zfs
    opnsense:
      api_url: https://fw.example.com
      api_key: xxxxxxxxxxxxxxxxxxxx
      api_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    kubernetes:
      kubeconfig_path: ~/.kube/config
      namespace: infra
  ```
- **Schema hints:**
  - `providers` (optional, list[str]): List of provider names to enable. If omitted, all registered providers are enabled.
  - `backend` (optional, dict): Terraform backend configuration for state management. Enables remote state storage and locking for team collaboration. See [State Management](../architecture/state-management.md#backend-configuration) for details.
    - `type` (required if backend specified): Backend type - `s3`, `gcs`, `azurerm`, `postgres`, `remote` (Terraform Cloud), or `local`
    - Type-specific fields:
      - **S3:** `bucket` (required), `key`, `region` (required), `dynamodb_table` (for locking), `encrypt`, `kms_key_id`, `profile`, `role_arn`
      - **GCS:** `bucket` (required), `prefix`, `credentials`, `encryption_key`
      - **Azure:** `resource_group_name` (required), `storage_account_name` (required), `container_name` (required), `key`, `access_key`, `sas_token`, `use_azuread_auth`
      - **Postgres:** `conn_str` (required), `schema_name`, `skip_schema_creation`
      - **Terraform Cloud:** `organization` (required), `workspaces` (required), `hostname`, `token`
  - `iac_tool` (optional, `"terraform"` | `"opentofu"`, default: `"terraform"`): Select the IaC provisioning tool. Can also be set via the `INFRAFOUNDRY_IAC_TOOL` environment variable (env var takes precedence). See [OpenTofu Runner](../runners/opentofu.md) for details.
  - `runner_priorities` (optional, dict[str, int]): Override default runner execution priorities. See [Runner Execution Overview](../runners/overview.md) for details.
  - `ssh.user`/`key_path`/`port` (optional, defaults to current user and port 22).
  - `provider_ssh.<provider>` overrides global SSH.
  - `provider_settings.<provider>` holds credentials/endpoints; fields vary by provider.
    - **Proxmox authentication:** Supports two methods:
      - Single token: `api_token: "user@pve!tokenid=secret"`
      - Separate fields: `api_token_id: "user@pve!tokenid"` + `api_token_secret: "secret"`
- **Generated outputs:** Values populate `generated/{env}/terraform/{provider}/terraform.tfvars` and Ansible vars automatically.

## Validation and Checks

- Run `infra validate --env <env> --check-api` to confirm structure and credentials.
- Inspect generated tfvars to verify SSH overrides and provider settings:
  ```bash
  cat generated/dev/terraform/proxmox/terraform.tfvars
  ```
- Ensure `settings.yaml` is encrypted and keys are git-ignored.

## Examples

- **Dev settings with minimal fields:**
  ```yaml
  name: dev
  description: Development environment
  provider_settings:
    proxmox:
      api_url: https://pve-dev.example.com:8006
      api_token: pve-dev-token
  ```
- **Selectively enable providers:**
  ```yaml
  name: prod
  description: Production environment - Proxmox only
  providers:
    - proxmox
  provider_settings:
    proxmox:
      api_url: https://pve-prod.example.com:8006
      api_token: pve-prod-token
  # Note: Only Proxmox provider will be loaded, even if opnsense/kubernetes
  # configs exist in the resources directory
  ```
- **Per-provider SSH override:**
  ```yaml
  provider_ssh:
    opnsense:
      user: opnsense-admin
      key_path: /secure/keys/opnsense_prod
      port: 22
  ```
- **Kubernetes settings:**
  ```yaml
  provider_settings:
    kubernetes:
      kubeconfig_path: ~/.kube/config
      namespace: platform
  ```
- **Proxmox dual authentication (separate token fields):**
  ```yaml
  provider_settings:
    proxmox:
      api_url: https://pve01.example.com:8006
      api_token_id: "automation@pve!infra-token"
      api_token_secret: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      node: pve01
      storage: local-zfs
  ```
- **S3 backend with DynamoDB locking:**
  ```yaml
  backend:
    type: s3
    s3:
      bucket: my-terraform-state
      key: prod/terraform.tfstate
      region: us-east-1
      dynamodb_table: terraform-locks
      encrypt: true
      kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012
  ```
- **Google Cloud Storage backend:**
  ```yaml
  backend:
    type: gcs
    gcs:
      bucket: my-tf-state-bucket
      prefix: prod/terraform/state
      credentials: /path/to/service-account-key.json
  ```
- **Azure Blob Storage backend:**
  ```yaml
  backend:
    type: azurerm
    azurerm:
      resource_group_name: terraform-state-rg
      storage_account_name: tfstatestorage
      container_name: tfstate
      key: prod.terraform.tfstate
      use_azuread_auth: true
  ```
- **PostgreSQL backend:**
  ```yaml
  backend:
    type: postgres
    postgres:
      conn_str: postgres://tfstate:password@db.example.com:5432/terraform_backend
      schema_name: prod_state
  ```
- **Terraform Cloud backend:**
  ```yaml
  backend:
    type: remote
    remote:
      organization: my-organization
      workspaces:
        name: prod-infrastructure
      # For Terraform Enterprise:
      # hostname: terraform.example.com
  ```

## Related Documentation

- [Configuration Guide](overview.md)
- [YAML-Only Configuration](yaml-only-config.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [SSH Authentication](../guides/ssh-authentication.md)
- [State Management & Backend Configuration](../architecture/state-management.md#backend-configuration)

## Troubleshooting

- **Symptom:** Missing values in generated tfvars. **Fix:** Ensure fields exist in `settings.yaml` and rerun `infra plan`.
- **Symptom:** SSH fails during Proxmox operations. **Fix:** Verify `ssh`/`provider_ssh` entries and key paths; re-validate with `--check-api`.
- **Symptom:** Secrets exposed in git. **Fix:** Encrypt `settings.yaml` with SOPS/age and confirm ignore rules include keys.
- **Symptom:** Provider not loading despite having resources defined. **Fix:** Check `providers` list in `settings.yaml`; if specified, only listed providers will be enabled.
- **Symptom:** Backend configuration validation fails. **Fix:** Run `infra backend validate --env <env>` for detailed error messages; ensure all required fields for the backend type are present (e.g., `bucket` and `region` for S3).
- **Symptom:** Terraform init fails with backend error. **Fix:** Verify backend resources exist (S3 bucket, DynamoDB table, GCS bucket, etc.); check credentials/permissions for accessing backend; confirm network connectivity to backend service.
- **Symptom:** No backend.tf generated. **Fix:** Ensure `backend` field exists in `settings.yaml`; local backend type does not generate backend.tf (this is expected behavior); verify backend type is not `local`.

---

Last updated: 2025-12-27 15:20 GMT


---
[Back to Table of Contents](../index.md)
