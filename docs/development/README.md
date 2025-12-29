# Development Guides

This section provides comprehensive guides for developing and extending InfraFoundry.

## Getting Started with Development

- **[Coding Standards](coding-standards.md)** - Style guides, conventions, and best practices for contributing code
- **[CI/CD Testing](ci-cd-testing.md)** - Continuous integration setup, testing strategies, and workflows
- **[Release & Automation](release-and-automation.md)** - Automated versioning, release management, and governance validation

## Extending InfraFoundry

### Core Extension Points

- **[Implementing Providers](implementing-providers.md)** - Guide for creating new infrastructure providers (Proxmox, OPNsense, etc.)
- **[Implementing Runners](implementing-runners.md)** - Comprehensive guide for creating custom infrastructure tool runners (Terraform, Ansible, etc.)
- **[Implementing Secret Providers](implementing-secret-providers.md)** - Guide to adding new secret storage backends (Vaultwarden, AWS, Azure, etc.)

### Quick References

- **[Runner Protocol Quick Reference](runner-protocol-quick-reference.md)** - Quick reference for protocol-based runner system implementation

## Architecture Patterns

- **[Manager Patterns](manager-patterns.md)** - Implementation patterns for Manager classes in the codebase
- **[Event System](event-system.md)** - Documentation of the internal event system for orchestration
- **[Credential Loader System](credential-loader-system.md)** - How the credential loading system works

## See Also

- [Architecture Overview](../architecture/overview.md) - High-level system architecture
- [AGENTS.md](../AGENTS.md) - Issue-driven development workflow
- [Examples](../examples/) - Working examples and tutorials

---

**Last Updated:** 2025-12-29
