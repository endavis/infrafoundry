---
title: "ADR-0017: Blueprint-declared requirements with a preflight check"
description: "Blueprints declare their Python and Ansible requirements, checked before any provider work and never installed during a run"
date: 2026-10-26
audience:
  - contributors
tags:
  - adr
---

# ADR-0017: Blueprint-declared requirements with a preflight check

## Status

Accepted

## Decision

A blueprint declares the Python packages and Ansible collections its event handlers and playbooks need, in an optional `requirements:` block in `blueprint.yaml`. The block holds PEP 508 specs, plus a path to an `ansible-galaxy` requirements file. It is independent of InfraFoundry's own `pyproject.toml` and extras.

Before any provider work, `Orchestrator.plan` (and through it `apply`) and `Orchestrator.destroy` check the requirements of every blueprint used by the packages in scope. That is the environment, narrowed by `--package` or `--provider`. An unmet requirement raises `MissingRequirementsError` (`IF-PACKAGE-002`), naming the requirement, the blueprints that need it and the install command. `config doctor` reports the same check for every environment.

Nothing is installed during a run. Installing is an explicit, separate step: the printed command, or `foundry deps sync` (#1047), which installs every unmet requirement in scope and checks again.

## Rationale

- **Fail before creating anything.** The `ontap-cluster` apply created both ONTAP VMs and the cluster, then failed in a post-cluster playbook on `No module named 'netapp_lib'`. That left the cluster half configured. A check that runs before the first provider call turns the same mistake into a refusal to start.
- **Not a core dependency.** Adding `netapp-lib` to `[project] dependencies` would ship it to every InfraFoundry install, including those with no NetApp package. A blueprint knows what its own handlers import, so the blueprint declares it.
- **No coupling to framework extras.** An extra per blueprint would tie the config repository's blueprint set to the framework's packaging. A blueprint added or edited in the config repo would need a framework release.
- **No auto-install during apply.** Installing packages from inside an infrastructure run mixes two failure domains. It also mutates the environment the run depends on, and needs network and write access the run should not assume. An explicit sync can be reviewed, cached and run once.
- **Scope follows the run.** Only blueprints of packages in scope are checked. An environment can run `--package` against one package without installing every other package's dependencies.
- **The orchestrator owns the check, not the CLI,** so programmatic use of the orchestrator gets it too.

### Considered and deferred

- **A config-repo-owned lockfile** (for example a `uv` project in the config repository) would pin exact versions for reproducible environments. It is deferred until a second consumer needs exact pins. The `requirements:` specs can feed such a lockfile later without changing blueprints.

### Known limit

The check verifies the interpreter running InfraFoundry. Ansible runs local-connection modules under the interpreter it discovers unless the inventory pins `ansible_python_interpreter` to `{{ ansible_playbook_python }}`. A blueprint whose modules need these packages must pin it; `ontap-cluster` does, in the inventory its post-terraform script generates (#1049).

## Related Issues

- Issue #1046: blueprint-declared requirements with a preflight check
- Issue #1047: `foundry deps sync` and `deps check`
- Issue #1048: move `netapp-lib` from core dependencies to the `ontap-cluster` blueprint
- Issue #1049: `ontap-cluster` runs NetApp modules under the system Python

## Related Documentation

- [Configuration Blueprints — The `requirements:` Block](../configuration/blueprints.md#the-requirements-block)
- [Error Reference — IF-PACKAGE-002](../reference/errors.md#if-package-002-blueprint-requirements-not-met)
- [CLI Reference — Deps Group](../usage/cli-reference.md#deps-group-foundry-deps)
