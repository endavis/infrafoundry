# direnv Setup for InfraFoundry

## Overview

`direnv` loads environment variables automatically based on the current directory, keeping InfraFoundry defaults and personal overrides in sync without manual exports.

## Audience and Prerequisites

- **Audience:** Local developers working on InfraFoundry or config repos.
- **Prereqs:** Shell access to install `direnv`, ability to edit shell init files, and the project root checked out.

## When to Use This

- You want project-scoped environment variables without editing your global shell profile.
- You need personal overrides (`.envrc.local`) that stay out of git.
- You want quick reloads after changing secrets or paths.

## Quick Start

1. Install `direnv`:
   - macOS: `brew install direnv`
   - Debian/Ubuntu: `sudo apt install direnv`
   - Others: follow https://direnv.net/docs/installation.html
2. Hook `direnv` into your shell (`~/.bashrc`, `~/.zshrc`, etc.):
   ```bash
   eval "$(direnv hook bash)"   # or zsh/fish equivalents
   ```
3. Allow the project and create personal overrides:
   ```bash
   cd /path/to/infrafoundry
   direnv allow
   cp docs/examples/.envrc.local.example .envrc.local
   # Edit .envrc.local with your credentials/preferences
   ```
4. Reload after edits:
   ```bash
   direnv reload
   ```

## Configuration Details

- **Files:**
  - `.envrc` — framework defaults (committed).
  - `.envrc.local` — personal overrides (git-ignored).
  - `docs/examples/.envrc.local.example` — starter template.
- **Behavior:** Entering the repo loads `.envrc` then `.envrc.local`; leaving unloads them. Credentials remain local.
- **Customizations:** Set `INFRAFOUNDRY_*`, provider credentials, Terraform/Ansible flags, or choose a Python version (`layout python python3.11`).

## Validation and Checks

- Verify load status: `direnv status`.
- Inspect variables: `printenv | grep INFRAFOUNDRY`.
- If changes do not apply, re-run `direnv allow` or `direnv reload`.

## Examples

- **Sample `.envrc.local`:**
  ```bash
  export INFRAFOUNDRY_CONFIG_REPO=$HOME/my-infra-config
  export INFRAFOUNDRY_LOG_LEVEL=DEBUG
  export KUBECONFIG=$HOME/.kube/config
  layout python python3.11
  ```
- **Temporary disable/enable:**
  ```bash
  direnv deny
  direnv allow
  ```

## Related Documentation

- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Configuration Guide](../configuration/overview.md)
- [YAML-Only Configuration](../configuration/yaml-only-config.md)

## Troubleshooting

- **Symptom:** `.envrc.local` not applied. **Fix:** Ensure the file exists, run `direnv allow`, then `direnv reload`.
- **Symptom:** Wrong Python version. **Fix:** Adjust `layout python ...` in `.envrc.local` and reload.
- **Symptom:** CI picks up direnv settings. **Fix:** Do not use direnv in CI; rely on CI env vars or `ci/setup-ci.sh`.

---

Last updated: 2025-12-23 14:19 GMT


---
[Back to Table of Contents](../index.md)
