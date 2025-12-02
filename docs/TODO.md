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



## Testing & Refactoring (from Maintenance Report)
- [x] **Unit Test Coverage: CLI Commands**: ([Issue](https://github.com/endavis/infrafoundry/issues/40))
- [ ] **Unit Test Coverage: Orchestration Workflows** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/41))
- [ ] **Unit Test Coverage: Deployment Executor** [Complexity: 6/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/42))
- [ ] **Unit Test Coverage: Runners** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/43))
- [ ] **Refactor & Test: Validators** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/44))
- [ ] **Refactor: Provider Terraform Generation** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/45))
- [x] **Refactor: Console Output**: ([Issue](https://github.com/endavis/infrafoundry/issues/46))
- [ ] **Refactor: Orchestrator God Class** [Complexity: 6/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/47))



## Architecture & Design (from Design Assessment)
- [ ] **Refactor: Use Protocol Classes** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/49))
- [x] **Documentation: Architecture Decision Records**: ([Issue](https://github.com/endavis/infrafoundry/issues/50))
- [x] **Documentation: Sequence Diagrams**: ([Issue](https://github.com/endavis/infrafoundry/issues/51))


## Code Quality & Refactoring (from Code Quality Analysis)
- [ ] **Refactor: BaseRunner Interface Segregation** [Complexity: 7/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/48))
- [x] **Refactor: KeaDHCPManager Duplication**: ([Issue](https://github.com/endavis/infrafoundry/issues/52))
- [ ] **Refactor: KeaClient CRUD Duplication** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/53))
- [ ] **Refactor: BaseProviderValidator** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/54))
- [x] **Refactor: Policy Evaluator Boilerplate** [Complexity: 3/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/55))
- [ ] **Refactor: Normalize OPNsense Interface Data** [Complexity: 3/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/56))
- [x] **Bug Fix: Print Statement in Policy Evaluator** [Complexity: 1/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/57))

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
