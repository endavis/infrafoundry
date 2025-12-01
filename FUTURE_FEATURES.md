# Future Features Roadmap

## Overview

Potential enhancements to expand InfraFoundry’s capabilities across templating, state, cost, automation, and security.

## Audience and Prerequisites

- **Audience:** Project contributors and roadmap stakeholders.
- **Prereqs:** Familiarity with current InfraFoundry features and architecture.

## When to Use This

- Planning contributions or prioritizing upcoming work.
- Aligning roadmap items with user needs (state, cost, drift, secrets).

## Quick Start (Completed/Planned)

- ✅ Configuration templating/blueprints
- ✅ Visual topology/graphing
- 🚧 State locking & remote backends
- 🚧 Cost estimation (FinOps)
- 🚧 Automated drift remediation
- 🚧 Secrets rotation
- 🚧 External vault integration

## Details

- **State locking & remote backend management:** Safe team collaboration; backend configs from `settings.yaml`; locking (e.g., S3/GCS/Postgres).
- **Cost estimation:** Integrate Infracost; budget-aware policies.
- **Automated drift remediation:** Periodic drift checks with optional auto-apply thresholds.
- **Secrets rotation:** `infra secrets rotate` to re-encrypt/update secrets.
- **External vault integration:** Expand `SecretProvider` implementations for Vault/AWS and others.

## Validation and Checks

- Ensure new features fit the pluggable architecture (providers, runners, secrets, policies).
- Add tests/coverage and docs updates with each feature.

## Related Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Secrets Architecture](docs/architecture/secrets-architecture.md)
- [Configuration Blueprints](docs/configuration/blueprints.md)
- [Policy Configuration Guide](docs/configuration/policy-configuration.md)

## Troubleshooting

- **Symptom:** Feature scope unclear. **Fix:** Open an issue/discussion to refine requirements and design.
- **Symptom:** Missing design alignment. **Fix:** Reference architecture docs and pluggable patterns before implementation.

---

Last updated: 2025-11-29 14:27 GMT
