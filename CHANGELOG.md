# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Config Init Command**: Added `foundry config init <env>` to create new environments, with `--from <existing>` flag to scaffold from existing environments.
- **Config Show Command**: Added `foundry config show --env <env>` to display resolved configuration with filtering by provider, resource type, and output format (table/yaml/json).
- **Error Code Catalog**: Added structured error codes (IF-CATEGORY-NNN) with actionable suggestions for all error types. Errors now display helpful resolution steps. See `docs/reference/errors.md` for full documentation.
- **External Vault Integration**: Added support for Vaultwarden/Bitwarden, AWS Secrets Manager, and Azure Key Vault as secret providers.
- **Dependency Analysis**: New command (`infra dependencies`?) to visualize and analyze resource dependencies.
- **Proxmox Config Exporter**: Tool to extract existing Proxmox cluster configurations into InfraFoundry YAML.
- **Config Diff Tool**: New command (`infra diff`) to compare configurations between environments or git revisions.
- **Visual Topology**: Added `infra graph` command to generate Mermaid diagrams of infrastructure topology.
- **Blueprints**: Added `infra new` command for creating resources from templates/blueprints.
- **PyInfra Support**: Added PyInfra as a supported runner for agentless configuration management.
- **Schema Validation**: Added rigorous schema validation for resource configurations using Pydantic/Validator schemas.

### Changed
- **CLI Error Handling**: Refactored error handling to use centralized error catalog. Removed `console` object and internal functions from `cli/decorators.py` (replaced by error catalog in `cli/errors.py`).

### Removed
- **`cli.decorators.console`**: Module-level `Console` object removed from `cli/decorators.py`. Use `cli.utils.console` instead if needed.
- **Provider Registry Service**: Extracted provider and runner registration logic into a dedicated `ProviderRegistryService` to decouple it from the Orchestrator.
- **Runner Interface**: Refactored runners to use Protocol-based interfaces (`Plannable`, `Applyable`, `Destroyable`) for better type safety and flexibility.
- **Task Runner**: Migrated development task runner from `just` to `doit` for better Python integration and cross-platform compatibility.
- **Validators**: Refactored provider validators into testable, modular components.
- **Console Output**: Standardized CLI output formatting using `rich` across all commands.
- **Terraform Generation**: Centralized and standardized Terraform code generation logic.
- **Orchestrator**: Refactored `Orchestrator` class to use dependency injection and reduce complexity (God Class refactor).
- **Documentation**: Comprehensive overhaul of documentation structure, including new guides for architecture, configuration, and runners.

### Fixed
- **Migration**: Fixed handling of `None` context objects in migration commands.
- **Tests**: Fixed path isolation issues in state backup and migration tests.
- **Policy Evaluator**: Reduced boilerplate and fixed output issues in policy evaluation.

## [0.1.0] - 2025-11-01
- Initial release of InfraFoundry framework.
