# Separate Configuration Repository Pattern

## Overview

Keep InfraFoundry framework code and infrastructure configs in distinct repositories. This pattern improves access control, versioning, and reuse while letting configs stay private and framework code remain shared.

## Audience and Prerequisites

- **Audience:** Operators and platform teams managing multiple environments or tenants.
- **Prereqs:** A cloned config repo (new or from `example-config`), ability to set `INFRAFOUNDRY_CONFIG_REPO` or use `--config-dir`, and SOPS/age for secrets.

## When to Use This

- You need private configs with shared/open framework code.
- Different teams own framework vs configs, or multiple config repos exist (dev/staging/prod/client).
- You want independent CI/CD and versioning for configs and framework.

## Quick Start

1. Create a config repo from the example:
   ```bash
   cp -r example-config ../my-infra-config
   cd ../my-infra-config
   git init && git add . && git commit -m "Initial configuration"
   ```
2. Point InfraFoundry to it:
   ```bash
   export INFRAFOUNDRY_CONFIG_REPO=$(pwd)   # or use --config-dir on commands
   ```
3. Run commands:
   ```bash
   infra validate --env dev --check-api --check-refs
   infra plan --env dev
   ```

## Configuration Details

- **Repository layout (config repo):**
  ```
  envs/
    dev/|staging/|prod/
      settings.yaml         # encrypted with SOPS/age
      resources/ or provider folders
      age.key (git-ignored)
  policies/                 # optional policy files
  notifications.yaml        # optional global notifications
  .sops.yaml                # per-env rules
  .envrc.local              # personal overrides (git-ignored)
  ```
- **Binding repo to CLI:** Prefer `INFRAFOUNDRY_CONFIG_REPO`. Alternatively, pass `--config-dir /path/to/config` to each `infra` command.
- **Access control:** Keep framework repo public/shared; keep config repo private with restricted key access.
- **Versioning:** Framework and configs can version independently; rollback configs without changing framework version; run separate CI/CD pipelines.
- **Multi-repo setups:** Use different config repos per tenant or environment; point `INFRAFOUNDRY_CONFIG_REPO` accordingly in direnv or shell exports.

## Validation and Checks

- Confirm the config path resolution by running:
  ```bash
  infra envs --config-dir /path/to/config
  ```
- Validate before plan/apply:
  ```bash
  infra validate --env dev --check-api --check-refs
  ```
- Ensure secrets are encrypted and keys are git-ignored.

## Examples

- **Direnv binding:**
  ```bash
  # .envrc.local in config repo
  export INFRAFOUNDRY_CONFIG_REPO=$(pwd)
  ```
- **One-off command with explicit config dir:**
  ```bash
  INFRAFOUNDRY_CONFIG_REPO=../my-infra-config infra plan --env prod
  # or
  infra --config-dir ../my-infra-config apply --env prod
  ```
- **Per-env SOPS rules (config repo `.sops.yaml`):**
  ```yaml
  creation_rules:
    - path_regex: envs/dev/settings\.yaml$
      age: <dev-public-key>
    - path_regex: envs/staging/settings\.yaml$
      age: <staging-public-key>
    - path_regex: envs/prod/settings\.yaml$
      age: <prod-public-key>
  ```

## Related Documentation

- [Configuration Guide](overview.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [Age Key Management Best Practices](../guides/age-key-management.md)
- [YAML-Only Configuration](yaml-only-config.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** CLI cannot find environments. **Fix:** Set `INFRAFOUNDRY_CONFIG_REPO` or use `--config-dir`; verify `envs/{env}` exists.
- **Symptom:** Secrets committed accidentally. **Fix:** Ensure `.sops.yaml` and ignore rules are present; rotate keys and re-encrypt.
- **Symptom:** Wrong repo picked up. **Fix:** Check direnv exports and shell session; echo `INFRAFOUNDRY_CONFIG_REPO` before running commands.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
