# Project To-Do & Roadmap

This document consolidates planned features, enhancements, and tools for InfraFoundry.

## Core Framework Enhancements

### State & Backends
- [ ] **State locking & remote backend management** [Complexity: 8/10]: Safe team collaboration; backend configs from `settings.yaml`; locking (e.g., S3/GCS/Postgres). ([Issue](https://github.com/endavis/infrafoundry/issues/30))
- [ ] **Automated drift remediation** [Complexity: 8/10]: Periodic drift checks with optional auto-apply thresholds. ([Issue](https://github.com/endavis/infrafoundry/issues/31))

### Cost & FinOps
- [ ] **Cost estimation** [Complexity: 6/10]: Integrate Infracost; budget-aware policies. ([Issue](https://github.com/endavis/infrafoundry/issues/32))

### Security
- [ ] **Secrets rotation** [Complexity: 9/10]: `infra secrets rotate` to re-encrypt/update secrets. ([Issue](https://github.com/endavis/infrafoundry/issues/33))
- [ ] **External vault integration** [Complexity: 7/10]: Expand `SecretProvider` implementations for Vault/AWS and others. ([Issue](https://github.com/endavis/infrafoundry/issues/34))

---

## Tooling Ecosystem

### Future Tools
- [x] **Proxmox Config Exporter** [Complexity: 5/10]: Extract Proxmox cluster configuration. ([Issue](https://github.com/endavis/infrafoundry/issues/35), [PR #74](https://github.com/endavis/infrafoundry/pull/74))
- [x] **Config Diff Tool** [Complexity: 4/10]: Compare configurations between environments. ([Issue](https://github.com/endavis/infrafoundry/issues/36), [PR #68](https://github.com/endavis/infrafoundry/pull/68))
- [x] **Resource Validator** [Complexity: 5/10]: Validate YAML configs against provider schemas. ([Issue](https://github.com/endavis/infrafoundry/issues/37), [PR #72](https://github.com/endavis/infrafoundry/pull/72))
- [ ] **Dependency Analyzer** [Complexity: 6/10]: Visualize resource dependencies. ([Issue](https://github.com/endavis/infrafoundry/issues/38))
- [ ] **Cost Calculator** [Complexity: 4/10]: Estimate infrastructure costs. ([Issue](https://github.com/endavis/infrafoundry/issues/39))

---



## Testing & Refactoring (from Maintenance Report)
- [x] **Unit Test Coverage: CLI Commands**: ([Issue](https://github.com/endavis/infrafoundry/issues/40), [PR #61](https://github.com/endavis/infrafoundry/pull/61))
- [x] **Unit Test Coverage: Orchestration Workflows** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/41), [PR #70](https://github.com/endavis/infrafoundry/pull/70))
- [x] **Unit Test Coverage: Deployment Executor** [Complexity: 6/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/42), [PR #71](https://github.com/endavis/infrafoundry/pull/71))
- [x] **Unit Test Coverage: Runners** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/43), [PR #69](https://github.com/endavis/infrafoundry/pull/69))
- [x] **Refactor & Test: Validators** [Complexity: 5/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/44), [PR #73](https://github.com/endavis/infrafoundry/pull/73))
- [ ] **Refactor: Provider Terraform Generation** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/45))
- [x] **Refactor: Console Output**: ([Issue](https://github.com/endavis/infrafoundry/issues/46), [PR #60](https://github.com/endavis/infrafoundry/pull/60))
- [ ] **Refactor: Orchestrator God Class** [Complexity: 6/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/47))



## Architecture & Design (from Design Assessment)
- [x] **Refactor: Use Protocol Classes** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/49), [PR #65](https://github.com/endavis/infrafoundry/pull/65))
- [x] **Documentation: Architecture Decision Records**: ([Issue](https://github.com/endavis/infrafoundry/issues/50), [PR #59](https://github.com/endavis/infrafoundry/pull/59))
- [x] **Documentation: Sequence Diagrams**: ([Issue](https://github.com/endavis/infrafoundry/issues/51), direct commit 4afac0c)


## Code Quality & Refactoring (from Code Quality Analysis)
- [ ] **Refactor: BaseRunner Interface Segregation** [Complexity: 7/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/48))
- [x] **Refactor: KeaDHCPManager Duplication**: ([Issue](https://github.com/endavis/infrafoundry/issues/52), [PR #58](https://github.com/endavis/infrafoundry/pull/58))
- [x] **Refactor: KeaClient CRUD Duplication** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/53), [PR #64](https://github.com/endavis/infrafoundry/pull/64))
- [x] **Refactor: BaseProviderValidator** [Complexity: 4/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/54), [PR #67](https://github.com/endavis/infrafoundry/pull/67))
- [x] **Refactor: Policy Evaluator Boilerplate** [Complexity: 3/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/55), [PR #62](https://github.com/endavis/infrafoundry/pull/62))
- [x] **Refactor: Normalize OPNsense Interface Data** [Complexity: 3/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/56), [PR #63](https://github.com/endavis/infrafoundry/pull/63))
- [x] **Bug Fix: Print Statement in Policy Evaluator** [Complexity: 1/10]: ([Issue](https://github.com/endavis/infrafoundry/issues/57), PR not recorded)

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
