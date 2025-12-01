# Project To-Do & Roadmap

This document consolidates planned features, enhancements, and tools for InfraFoundry.

## Core Framework Enhancements

### State & Backends
- [ ] **State locking & remote backend management**: Safe team collaboration; backend configs from `settings.yaml`; locking (e.g., S3/GCS/Postgres). ( - Complexity: 8)
- [ ] **Automated drift remediation**: Periodic drift checks with optional auto-apply thresholds. ( - Complexity: 8)

### Cost & FinOps
- [ ] **Cost estimation**: Integrate Infracost; budget-aware policies. ( - Complexity: 6)

### Security
- [ ] **Secrets rotation**: `infra secrets rotate` to re-encrypt/update secrets. ( - Complexity: 9)
- [ ] **External vault integration**: Expand `SecretProvider` implementations for Vault/AWS and others. ( - Complexity: 7)

---

## Tooling Ecosystem

### Future Tools
- [ ] **Proxmox Config Exporter**: Extract Proxmox cluster configuration. ( - Complexity: 5)
- [ ] **Config Diff Tool**: Compare configurations between environments. ( - Complexity: 4)
- [ ] **Resource Validator**: Validate YAML configs against provider schemas. ( - Complexity: 5)
- [ ] **Dependency Analyzer**: Visualize resource dependencies. ( - Complexity: 6)
- [ ] **Cost Calculator**: Estimate infrastructure costs. ( - Complexity: 4)

---



## Testing & Refactoring (from Maintenance Report)
- [ ] **Unit Test Coverage: CLI Commands**: ( - Complexity: 3)
- [ ] **Unit Test Coverage: Orchestration Workflows**: ( - Complexity: 5)
- [ ] **Unit Test Coverage: Deployment Executor**: ( - Complexity: 6)
- [ ] **Unit Test Coverage: Runners**: ( - Complexity: 5)
- [ ] **Refactor & Test: Validators**: ( - Complexity: 5)
- [ ] **Refactor: Provider Terraform Generation**: ( - Complexity: 4)
- [ ] **Refactor: Console Output**: ( - Complexity: 2)
- [ ] **Refactor: Orchestrator God Class**: ( - Complexity: 6)



## Architecture & Design (from Design Assessment)
- [ ] **Refactor: Use Protocol Classes**: ( - Complexity: 4)
- [ ] **Documentation: Architecture Decision Records**: ( - Complexity: 2)
- [ ] **Documentation: Sequence Diagrams**: ( - Complexity: 3)


## Code Quality & Refactoring (from Code Quality Analysis)
- [ ] **Refactor: BaseRunner Interface Segregation**: ( - Complexity: 7)
- [ ] **Refactor: KeaDHCPManager Duplication**: ( - Complexity: 2)
- [ ] **Refactor: KeaClient CRUD Duplication**: ( - Complexity: 4)
- [ ] **Refactor: BaseProviderValidator**: ( - Complexity: 4)
- [ ] **Refactor: Policy Evaluator Boilerplate**: ( - Complexity: 3)
- [ ] **Refactor: Normalize OPNsense Interface Data**: ( - Complexity: 3)
- [ ] **Bug Fix: Print Statement in Policy Evaluator**: ( - Complexity: 1)

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
