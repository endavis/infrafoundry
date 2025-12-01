# Project To-Do & Roadmap

This document consolidates planned features, enhancements, and tools for InfraFoundry.

## Core Framework Enhancements

### State & Backends
- [ ] **State locking & remote backend management**: Safe team collaboration; backend configs from `settings.yaml`; locking (e.g., S3/GCS/Postgres).
- [ ] **Automated drift remediation**: Periodic drift checks with optional auto-apply thresholds.

### Cost & FinOps
- [ ] **Cost estimation**: Integrate Infracost; budget-aware policies.

### Security
- [ ] **Secrets rotation**: `infra secrets rotate` to re-encrypt/update secrets.
- [ ] **External vault integration**: Expand `SecretProvider` implementations for Vault/AWS and others.

---

## Tooling Ecosystem

### Future Tools
- [ ] **Proxmox Config Exporter**: Extract Proxmox cluster configuration.
- [ ] **Config Diff Tool**: Compare configurations between environments.
- [ ] **Resource Validator**: Validate YAML configs against provider schemas.
- [ ] **Dependency Analyzer**: Visualize resource dependencies.
- [ ] **Cost Calculator**: Estimate infrastructure costs.

---

## Completed Features
- [x] Configuration templating/blueprints
- [x] Visual topology/graphing

---

## Related Documentation
- [Architecture Overview](architecture/overview.md)
- [Secrets Architecture](architecture/secrets-architecture.md)
- [Configuration Blueprints](configuration/blueprints.md)
- [Policy Configuration Guide](configuration/policy-configuration.md)

---
[Back to Table of Contents](TABLE_OF_CONTENTS.md)
