# Example: .envrc.local

## Overview

This example shows a personal `.envrc.local` for direnv to load InfraFoundry config paths and credentials locally.

## Audience and Prerequisites

- **Audience:** Developers using direnv for local InfraFoundry work.
- **Prereqs:** direnv installed and allowed in the repo; access to your config repo and credentials.

## When to Use This

- Setting per-user overrides for config repo paths and log levels.
- Storing provider credentials locally (never committed).

## Quick Start

1. Copy the example:
   ```bash
   cp docs/examples/.envrc.local.example .envrc.local
   ```
2. Edit values for your environment and allow direnv:
   ```bash
   direnv allow
   ```

## Configuration Details

- **Variables:** Point `INFRAFOUNDRY_CONFIG_REPO` to your config repo; set log levels and provider creds.
- **Location:** `.envrc.local` at repo root; git-ignored.

## Validation and Checks

- Run `direnv status` to confirm variables are loaded.
- Verify `printenv | grep INFRAFOUNDRY` shows expected values.

## Examples

- **Sample content:**
  ```bash
  export INFRAFOUNDRY_CONFIG_REPO=$HOME/my-infra-config
  export INFRAFOUNDRY_LOG_LEVEL=INFO
  export PROXMOX_API_URL=https://pve.example.com:8006/api2/json
  export PROXMOX_API_TOKEN_ID=user@pam!token
  export PROXMOX_API_TOKEN_SECRET=super-secret
  ```

## Related Documentation

- [direnv Setup](../direnv.md)
- [Per-Environment Credentials](../per-environment-credentials.md)
- [Configuration Guide](../configuration.md)

## Troubleshooting

- **Symptom:** Variables not applied. **Fix:** Ensure `.envrc.local` exists, run `direnv allow`, then `direnv reload`.
- **Symptom:** Credentials missing. **Fix:** Export provider credentials in `.envrc.local`; keep file git-ignored.

---

Last updated: 2025-11-29 14:27 GMT
