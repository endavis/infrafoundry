# Per-Environment Credentials

## Overview

InfraFoundry automatically loads credentials for the environment you target with `--env`, decrypting `settings.yaml` and exporting provider variables so you do not have to switch shells or profiles manually.

## Audience and Prerequisites

- **Audience:** Config repo maintainers and operators deploying to multiple environments.
- **Prereqs:** Config repo with `envs/{env}`, `sops` + `age` installed, per-environment age keys (git-ignored), and `uv run infra` available.

## When to Use This

- Running plan/apply across dev/staging/prod with isolated credentials.
- Rotating or auditing credentials per environment.
- Ensuring teams only access the environments they own.

## Quick Start

1. Generate age keys and ignore them:
   ```bash
   age-keygen -o envs/dev/age.key
   age-keygen -o envs/staging/age.key
   age-keygen -o envs/prod/age.key
   printf "envs/*/age.key\nenvs/**/age.key\n" >> .gitignore
   ```
2. Add per-environment rules to `.sops.yaml`:
   ```yaml
   creation_rules:
     - path_regex: envs/dev/settings\.yaml$
       age: <dev-public-key>
     - path_regex: envs/staging/settings\.yaml$
       age: <staging-public-key>
     - path_regex: envs/prod/settings\.yaml$
       age: <prod-public-key>
   ```
3. Add credentials to `envs/{env}/settings.yaml` under `provider_settings`, then encrypt:
   ```bash
   sops --encrypt --in-place envs/dev/settings.yaml
   ```
4. Run commands; InfraFoundry picks credentials for the specified env:
   ```bash
   infra plan --env dev
   infra apply --env prod
   ```

## Configuration Details

- **Automatic loading:** `infra ... --env <env>` decrypts `envs/{env}/settings.yaml`, extracts `provider_settings`, and exports provider environment variables (e.g., `PROXMOX_API_URL`, `OPNSENSE_API_KEY`).
- **Recommended structure:**
  ```
  config-repo/
  ├── .sops.yaml
  └── envs/
      ├── dev/
      │   ├── age.key               # git-ignored
      │   ├── settings.yaml         # encrypted
      │   └── resources/
      ├── staging/
      │   ├── age.key
      │   ├── settings.yaml
      │   └── resources/
      └── prod/
          ├── age.key
          ├── settings.yaml
          └── resources/
  ```
- **Age key selection:** Point `SOPS_AGE_KEY_FILE` to the environment key (manually or in `.envrc.local`); InfraFoundry uses the matching key for the `--env` you run.
- **Access control:** Restrict prod keys; store keys in Vault/Secrets Manager/1Password/Bitwarden where possible.

## Validation and Checks

- Ensure keys are ignored: `git status --ignored | grep age.key` should show ignored paths only.
- Confirm encryption works: `sops --decrypt envs/dev/settings.yaml >/dev/null`.
- Run `infra validate --env <env> --check-api` to confirm credentials work against provider endpoints.

## Examples

- **Sample `settings.yaml` for dev:**
  ```yaml
  name: dev
  description: Development environment
  provider_settings:
    proxmox:
      api_url: https://pve-dev.example.com:8006
      api_token_id: terraform@pve!dev
      api_token_secret: dev-secret
    opnsense:
      api_url: https://fw-dev.example.com
      api_key: dev-api-key
      api_secret: dev-api-secret
  ```
- **Prod run with explicit key:**
  ```bash
  SOPS_AGE_KEY_FILE=envs/prod/age.key infra plan --env prod
  ```
- **Credential rotation:** Update `settings.yaml`, re-encrypt with SOPS, and rerun `infra validate --check-api`.

## Related Documentation

- [Age Key Management Best Practices](../guides/age-key-management.md)
- [Configuration Guide](overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Secrets Architecture](../architecture/secrets-architecture.md)
- [Separate Config Repo](separate-config-repo.md)

## Troubleshooting

- **Symptom:** InfraFoundry reports missing credentials. **Fix:** Ensure `settings.yaml` has `provider_settings` for the provider and is encrypted with the correct key for that env.
- **Symptom:** Decryption fails. **Fix:** Set `SOPS_AGE_KEY_FILE` to the right env key; verify `.sops.yaml` creation rules.
- **Symptom:** Wrong environment credentials used. **Fix:** Confirm `--env` flag and that you are invoking from the intended config repo; check `INFRAFOUNDRY_CONFIG_REPO` or `--config-dir`.

---

Last updated: 2025-11-29 14:19 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
