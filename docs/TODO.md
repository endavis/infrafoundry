# Project To-Do & Roadmap

This document consolidates planned features, enhancements, and tools for InfraFoundry.

## Core Framework Enhancements

### State & Backends
- [ ] **State locking & remote backend management**: Safe team collaboration; backend configs from `settings.yaml`; locking (e.g., S3/GCS/Postgres). ([Issue](https://github.com/endavis/infrafoundry/issues/30))
- [ ] **Automated drift remediation**: Periodic drift checks with optional auto-apply thresholds. ([Issue](https://github.com/endavis/infrafoundry/issues/31))

### Cost & FinOps
- [ ] **Cost estimation**: Integrate Infracost; budget-aware policies. ([Issue](https://github.com/endavis/infrafoundry/issues/32))

### Security
- [ ] **Secrets rotation**: `infra secrets rotate` to re-encrypt/update secrets. ([Issue](https://github.com/endavis/infrafoundry/issues/33))
- [ ] **External vault integration**: Expand `SecretProvider` implementations for Vault/AWS and others. ([Issue](https://github.com/endavis/infrafoundry/issues/34))

---

## Tooling Ecosystem

### Future Tools
- [ ] **Proxmox Config Exporter**: Extract Proxmox cluster configuration. ([Issue](https://github.com/endavis/infrafoundry/issues/35))
- [ ] **Config Diff Tool**: Compare configurations between environments. ([Issue](https://github.com/endavis/infrafoundry/issues/36))
- [ ] **Resource Validator**: Validate YAML configs against provider schemas. ([Issue](https://github.com/endavis/infrafoundry/issues/37))
- [ ] **Dependency Analyzer**: Visualize resource dependencies. ([Issue](https://github.com/endavis/infrafoundry/issues/38))
- [ ] **Cost Calculator**: Estimate infrastructure costs. ([Issue](https://github.com/endavis/infrafoundry/issues/39))

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
