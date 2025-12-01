# Validation and Pre-Flight Checks

## Overview

InfraFoundry validation catches configuration, reference, and connectivity issues **before** `infra plan` or `infra apply` to keep deployments safe and predictable.

## Audience and Prerequisites

- **Audience:** Operators and CI pipelines running plan/apply workflows.
- **Prereqs:** Config repo available, `uv run infra` installed, provider credentials and network access for targeted environments.

## When to Use This

- Before any plan/apply, especially for production changes.
- After editing settings, resources, or secrets to ensure structural integrity.
- In CI to block merges when validation fails.

## Quick Start

```bash
infra validate --env dev
infra validate --env prod --check-api --check-refs
```

- `--check-api` validates provider endpoints and credentials.
- `--check-refs` validates referenced templates, networks, aliases, namespaces, and other dependencies.

## Configuration Details

- **Command:** `infra validate --env <env> [--check-api] [--check-refs]`
- **Environment discovery:** Uses `--env` with `--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`.
- **Severity levels:** `ERROR` (blocks), `WARNING` (review), `INFO` (informational).
- **Always checked:** YAML syntax, environment structure (`settings.yaml`, resource files), supported provider/resource types, provider registration, required fields.
- **API checks:** Proxmox (endpoint/token/node), OPNsense (endpoint/key/secret/firewall), Kubernetes (kubeconfig/cluster/namespace).
- **Reference checks:** Templates, networks/bridges/storage (Proxmox); aliases/VLANs/interfaces (OPNsense); namespaces/configmaps/secrets (Kubernetes).

## Validation and Checks

- Run baseline checks with `infra validate --env <env>`.
- Add `--check-api` to surface credential or connectivity issues early.
- Add `--check-refs` to ensure referenced resources exist before plan/apply.
- Output summarizes per-provider checks and reports blocking `ERROR` entries.

## Examples

- **Basic validation:**
  ```bash
  infra validate --env dev
  ```
- **Pre-deployment validation with external checks:**
  ```bash
  infra validate --env prod --check-api --check-refs
  ```
- **CI usage (GitHub Actions excerpt):**
  ```yaml
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: infra validate --env prod --check-api --check-refs
  ```
- **Provider extension (custom connectivity check):**
  ```python
  class MyProvider(ProviderBase):
      def validate_connectivity(self, env_config: dict[str, Any], report: ValidationReport) -> None:
          api_url = env_config["provider_settings"]["myprovider"]["api_url"]
          response = requests.get(f"{api_url}/health")
          passed = response.status_code == 200
          level = ValidationLevel.INFO if passed else ValidationLevel.ERROR
          message = "Connected" if passed else f"API returned {response.status_code}"
          report.add_check("myprovider_connectivity", passed=passed, message=message, level=level)
  ```

## Related Documentation

- [CLI Reference](cli-reference.md)
- [Settings File Structure](../configuration/settings-file-structure.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [State Management](../architecture/state-management.md)

## Troubleshooting

- **Symptom:** Missing templates/networks. **Fix:** Create the resource in the provider or update the reference; rerun with `--check-refs`.
- **Symptom:** API check failures. **Fix:** Verify endpoints, tokens, kubeconfig, and network reachability; test with provider CLIs.
- **Symptom:** Unknown resource/provider. **Fix:** Confirm resource type spelling and provider availability in the current framework version.

---

Last updated: 2025-11-29 14:12 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
