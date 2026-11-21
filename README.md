# InfraFoundry

[![CI](https://github.com/endavis/infrafoundry/actions/workflows/ci.yml/badge.svg)](https://github.com/endavis/infrafoundry/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/endavis/infrafoundry/branch/main/graph/badge.svg)](https://codecov.io/gh/endavis/infrafoundry)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

A pluggable infrastructure code generator and orchestration framework that turns YAML into Terraform/Ansible, with optional execution, state tracking, policies, and notifications.

## When to Use This

- You want YAML-only definitions that generate Terraform/Ansible for multi-provider environments.
- You need reproducible, policy-enforced plans/applies with state/history and notifications.
- You prefer separating the framework from your configuration repository.

**Audience:** platform and infrastructure engineers operating InfraFoundry. **Prerequisites:** Python 3.13+, `uv`, Terraform ≥1.6 or OpenTofu ≥1.6, Ansible ≥2.15, SOPS + age, and a config repo (`INFRAFOUNDRY_CONFIG_REPO` or `--config-dir`). The setup script below installs the tools.

## Features

- **Providers:** AWS, ESXi, host (existing machines, configured with Ansible), Kubernetes, MikroTik, OCI, OpenWrt, OPNsense, Proxmox and Tailscale. Providers are pluggable, so you can add your own.
- **Secrets:** SOPS/age, Vaultwarden/Bitwarden, AWS Secrets Manager and Azure Key Vault backends.
- **YAML-only configuration** that generates Terraform and Ansible artifacts.
- **Separate config repos**, with GitHub and GitLab CI/CD examples.
- **State and history tracking** in SQLite or PostgreSQL.
- **Orchestration extras:** an event system with notifications, policy enforcement, drift detection and dependency graphing.
- **Blueprints** that scaffold reusable infrastructure patterns.

## Quick Start

```bash
git clone https://github.com/endavis/infrafoundry.git
cd infrafoundry

# Installs uv if missing, the project (editable), and, through `doit install_deps`,
# direnv, age, SOPS, Terraform and Ansible
./scripts/setup-dependencies.sh

# Interactive wizard: pick a config location (local example-config/ or a new separate
# repository), name an environment, and answer prompts for Proxmox, OPNsense, network
# and optional Tailscale settings. It writes the environment's YAML files.
./scripts/setup-config.sh
```

If the wizard created a separate config repository, point InfraFoundry at it with
`export INFRAFOUNDRY_CONFIG_REPO=/path/to/my-infra-config`; otherwise pass `--config-dir example-config`
(CLI precedence: explicit flag, then environment variable, then local `./envs`). Then run the
[everyday flow](#everyday-command-flow) below with your environment name. Review the generated YAML
and set up secrets first (`uv run foundry secrets init`); see the
[Setup Guide](docs/getting-started/setup-guide.md) for the full walkthrough.

## Core Concepts

- **Framework repo vs config repo:** this repository holds the code, provider plugins and templates. Your infrastructure definitions and secrets live in a separate config repository. See [Separate Config Repo](docs/configuration/separate-config-repo.md).
- **Environments:** each environment (for example `dev` or `prod`) is a directory in the config repo with its own settings, resources and keys.
- **Packages:** self-contained directories that bundle resource templates, variables and event handlers into one deployable unit. See [Infrastructure Packages](docs/configuration/infrastructure-packages.md).
- **Blueprints:** reusable patterns that scaffold a configuration or service (`foundry config new create <blueprint> <dir>`). See [Blueprints](docs/configuration/blueprints.md).
- **Secrets:** encrypted per environment with SOPS and age, or held in Vaultwarden, AWS Secrets Manager or Azure Key Vault. See [Secrets Architecture](docs/architecture/secrets-architecture.md).

## Everyday Command Flow

Run through `uv run foundry ...` (or `foundry ...` with the environment activated):

```bash
foundry doctor                    # check Terraform/OpenTofu, Ansible, SOPS and age are installed
foundry config doctor             # check the config repo: structure, state, keys, blueprints
foundry infra doctor --env dev    # validate the environment against the provider APIs
foundry infra plan --env dev      # generate files and show what would change
foundry infra apply --env dev     # generate and execute Terraform/Ansible
```

`foundry --help` lists every command group: `config`, `infra`, `state`, `secrets`, `policy`, `deps`
and `provider`. See the [CLI Reference](docs/usage/cli-reference.md).

## Documentation

The full documentation is in [docs/](docs/index.md). Build and view it locally with `uv run doit docs_serve`.

| Section | What is there |
| :--- | :--- |
| [Getting Started](docs/getting-started/setup-guide.md) | Setup guide and [direnv](docs/getting-started/direnv.md) integration |
| [Configuration](docs/configuration/overview.md) | Config layout, packages, blueprints, secrets backends, policies, notifications |
| [Providers](docs/providers/proxmox.md) | One page per provider: [AWS](docs/providers/aws.md), [ESXi](docs/providers/esxi.md), [Host](docs/providers/host.md), [Kubernetes](docs/providers/kubernetes.md), [MikroTik](docs/providers/mikrotik.md), [OCI](docs/providers/oci.md), [OpenWrt](docs/providers/openwrt.md), [OPNsense](docs/providers/opnsense.md), [Proxmox](docs/providers/proxmox.md), [Tailscale](docs/providers/tailscale.md) |
| [Usage](docs/usage/cli-reference.md) | [CLI reference](docs/usage/cli-reference.md), [validation](docs/usage/validation.md), [error codes](docs/reference/errors.md), [troubleshooting](docs/guides/troubleshooting.md) |
| [Guides](docs/guides/ssh-authentication.md) | Task-focused walkthroughs such as SSH authentication, drift detection and migrations |
| [Architecture](docs/architecture/overview.md) | System overview, state management, orchestrator, runners, decision records |
| [Development](docs/development/README.md) | Contributor setup, tasks, tests, releases, AI agent setup and extending InfraFoundry |

## Contributing

Contributor setup, `doit` tasks, tests, releases and AI agent support are documented in
[docs/development/](docs/development/README.md); start with
[Contributor Setup](docs/development/contributor-setup.md). The workflow, commit format and
coverage rules are in [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md). See
[CHANGELOG.md](CHANGELOG.md) for release history.

## Support

- Issues/Discussions: [github.com/endavis/infrafoundry](https://github.com/endavis/infrafoundry)
- Docs: [docs/](docs/index.md) in repo

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
