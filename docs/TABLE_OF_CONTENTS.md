# InfraFoundry Documentation

This index provides a structured overview of the available documentation.

## Getting Started
- **[Setup Guide](getting-started/setup-guide.md)**: Step-by-step instructions for installing and setting up InfraFoundry.
- **[Direnv Integration](getting-started/direnv.md)**: How to configure and use `direnv` for automatic environment variable management.

## Usage
- **[CLI Reference](usage/cli-reference.md)**: Comprehensive reference for the `infra` command-line interface.
- **[Validation](usage/validation.md)**: Guide to running pre-flight checks and validating configurations.

## Configuration
- **[Overview](configuration/overview.md)**: High-level introduction to configuring InfraFoundry.
- **[Settings File Structure](configuration/settings-file-structure.md)**: Detailed specification of the settings file layout.
- **[YAML Only Config](configuration/yaml-only-config.md)**: Guide to using the pure YAML configuration approach.
- **[Per-Environment Credentials](configuration/per-environment-credentials.md)**: Managing credentials specific to different environments.
- **[Policy Configuration](configuration/policy-configuration.md)**: Defining and enforcing infrastructure policies.
- **[Separate Config Repo](configuration/separate-config-repo.md)**: Best practices for maintaining configurations in a separate repository.
- **[Notifications](configuration/notifications.md)**: Setting up and customizing system notifications.
- **[Blueprints](configuration/blueprints.md)**: Using blueprints for reusable infrastructure patterns.

## Architecture
- **[Overview](architecture/overview.md)**: Conceptual overview of the system architecture.
- **[Detailed Architecture](architecture/ARCHITECTURE.md)**: Deep dive into the architectural components and their interactions.
- **[State Management](architecture/state-management.md)**: Explanation of how InfraFoundry manages and tracks state.
- **[Secrets Architecture](architecture/secrets-architecture.md)**: Design and implementation of the secure secrets management system.
- **[Orchestrator](architecture/orchestrator-architecture.md)**: Architecture of the orchestration engine.
- **[Pluggable Runners](architecture/pluggable-runners.md)**: How the runner system supports multiple backends (Terraform, Ansible, etc.).
- **[Graphing](architecture/graphing.md)**: Details on dependency graphing and visualization capabilities.
- **[Design Principles](architecture/principles.md)**: Core principles guiding the design of InfraFoundry.
- **[Design Principles Assessment](architecture/design-principles-assessment.md)**: Evaluation of the architecture against the design principles.
- **[Architectural Patterns](architecture/architectural-patterns.md)**: Common software patterns employed in the codebase.

## Guides
- **[ISC to Kea Migration](guides/isc-to-kea-migration.md)**: Walkthrough for migrating DHCP services from ISC to Kea.
- **[DHCP VM Integration](guides/dhcp-vm-integration.md)**: Integrating DHCP services with Virtual Machines.
- **[Age Key Management](guides/age-key-management.md)**: Managing Age encryption keys for secrets.
- **[SSH Authentication](guides/ssh-authentication.md)**: Setting up and managing SSH authentication.

## Development
- **[Implementing Providers](development/implementing-providers.md)**: Guide for creating new providers for InfraFoundry.
- **[Manager Patterns](development/manager-patterns.md)**: implementation patterns for Manager classes.
- **[Event System](development/event-system.md)**: Documentation of the internal event system.
- **[Credential Loader](development/credential-loader-system.md)**: How the credential loading system works.
- **[Coding Standards](development/coding-standards.md)**: Style guides and standards for contributing code.
- **[CI/CD Testing](development/ci-cd-testing.md)**: Strategies and setups for CI/CD pipelines.
- **[Implementing Secret Providers](development/implementing-secret-providers.md)**: Guide to adding new secret storage providers.

## Runners
- **[Overview](runners/overview.md)**: Introduction to the runner subsystem.
- **[Ansible](runners/ansible.md)**: Specifics of the Ansible runner implementation.
- **[Terraform](runners/terraform.md)**: Specifics of the Terraform runner implementation.
- **[PyInfra](runners/pyinfra.md)**: Specifics of the PyInfra runner implementation.

## Examples
- **[Env Example](examples/ENV_EXAMPLE.md)**: Annotated example of environment configuration.
- **[Envrc Local](examples/ENVRC_LOCAL.md)**: Example usage of local environment variables.
- **[Gitlab CI](examples/GITLAB_CI_EXAMPLE.md)**: Example GitLab CI workflow configuration.

## Tools
- **[OpnSense Parser](tools/opnsense-parser.md)**: Documentation for the OpnSense configuration parser.

## Testing
- **[Maintenance Report](testing/TESTING_MAINTENANCE_REPORT.md)**: Status and maintenance notes for the test suite.

## Meta
- **[Documentation Template](meta/documentation-template.md)**: Standard template for new documentation files.
- **[Code Quality Analysis](meta/code-quality-analysis.md)**: Reports and metrics on code quality.
