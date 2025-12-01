# Example: .env

## Overview

This example illustrates a legacy `.env` file for CI/local use, defining InfraFoundry config paths and credentials via environment variables.

## Audience and Prerequisites

- **Audience:** CI maintainers or developers not using direnv.
- **Prereqs:** Ability to export environment variables in your shell or CI system; access to provider credentials.

## When to Use This

- Supplying InfraFoundry variables in CI jobs or non-direnv setups.
- Quickly setting defaults for local testing.

## Quick Start

1. Copy the example:
   ```bash
   cp docs/examples/.env.example .env
   ```
2. Update values and source the file:
   ```bash
   set -a
   source .env
   set +a
   ```

## Configuration Details

- **Variables:** `INFRAFOUNDRY_CONFIG_REPO`, log level, provider credentials (`PROXMOX_*`, etc.).
- **Location:** At repo root; adjust paths for CI runners or local shells.

## Validation and Checks

- Run `printenv | grep INFRAFOUNDRY` to confirm values.
- Ensure credentials are available before running `infra` commands.

## Examples

- **Sample content:**
  ```bash
  export INFRAFOUNDRY_CONFIG_REPO=/home/user/my-infra-config
  export INFRAFOUNDRY_LOG_LEVEL=INFO
  export PROXMOX_API_URL=https://pve.example.com:8006/api2/json
  export PROXMOX_API_TOKEN_ID=user@pam!token
  export PROXMOX_API_TOKEN_SECRET=super-secret
  ```

## Related Documentation

- [Configuration Guide](../configuration/overview.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [CI/CD Testing Guide](../development/ci-cd-testing.md)

## Troubleshooting

- **Symptom:** Vars not loaded. **Fix:** Ensure the file is sourced (`set -a; source .env; set +a`) or exported in CI environment.
- **Symptom:** Wrong config repo path. **Fix:** Update `INFRAFOUNDRY_CONFIG_REPO` to the correct location for the runner/host.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
