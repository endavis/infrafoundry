# InfraFoundry

## Overview

A pluggable infrastructure code generator and orchestration framework that turns YAML into Terraform/Ansible, with optional execution, state tracking, policies, and notifications.

## Audience and Prerequisites

- **Audience:** Platform/infrastructure engineers and contributors building or operating InfraFoundry.
- **Prereqs:** Python 3.12+, `uv`, Terraform ≥1.6, Ansible ≥2.15, SOPS + age, direnv (optional), and access to a config repo (`INFRAFOUNDRY_CONFIG_REPO` or `--config-dir`).

## When to Use This

- You want YAML-only definitions that generate Terraform/Ansible for multi-provider environments.
- You need reproducible, policy-enforced plans/applies with state/history and notifications.
- You prefer separating framework and configuration repositories.

## Quick Start

```bash
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry
./scripts/setup-dependencies.sh
./scripts/setup-config.sh
infra validate --env dev --check-api --check-refs
infra plan --env dev
infra apply --env dev
```

## Features

- Pluggable providers (Proxmox, OPNsense, Kubernetes; extensible)
- Pluggable secrets (SOPS/age default; Vault/AWS/custom via SecretProvider)
- YAML-only configuration; generated Terraform/Ansible artifacts
- Separate config repos; CI/CD-ready with GitHub/GitLab examples
- State/history tracking (SQLite/PostgreSQL)
- Event system + notifications; policy enforcement; drift detection; dependency graphing

## Documentation

- Getting started: [CLI Reference](docs/CLI_REFERENCE.md), [Setup Guide](docs/SETUP_GUIDE.md), [Architecture Overview](docs/architecture/overview.md)
- Core guides: Configuration, secrets, notifications, state, policies, migrations, direnv (see `docs/`)
- Development: Plugin/secret providers, credential loader, event system, manager patterns, CI/CD testing
- Tools: [OPNsense Parser](docs/tools/opnsense-parser.md)

## Contributing

- Use Conventional Commits; maintain ≥69% coverage.
- Run locally: `doit format && doit lint && uv run pytest` (or `doit coverage`).
- See `docs/development/ci-cd-testing.md` and `docs/development/coding-standards.md`.

## Support

- Issues/Discussions: project GitHub
- Docs: `docs/` in repo

---

Last updated: 2025-11-29 14:27 GMT
