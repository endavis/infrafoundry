---
title: "Troubleshooting Common Errors"
description: "Find the cause and fix for common foundry errors by symptom, with links to the error reference"
audience:
  - users
tags:
  - guides
  - troubleshooting
---

# Troubleshooting Common Errors

## Overview

Start from the symptom. Each entry gives the likely cause, the fix and a link to the [Error Reference](../reference/errors.md) where an `IF-` code exists.

## How Errors Are Shown

A failing command prints an error in this shape (`ErrorInfo.format_message` in `src/infrafoundry/cli/errors.py`):

```text
[IF-CONFIG-001] Environment Not Found
  <the original message>

  Suggestions:
    - <suggestion>

  See: <reference, when the code has one>

  Run with --debug for full error details.
```

The code comes from the exception's class name, or from the nearest parent class that has a code. An exception with no code is shown as `IF-GENERAL-001`, "Unknown Error". Run the command again with `--debug` for the full details.

!!! note "Suggestions can name commands that do not exist"
    A few suggestions in the printed text name commands the CLI does not have as written, for example `foundry config validate`, `foundry state reset` and a top-level `foundry analyze`. The commands on this page are the ones `foundry --help` lists. `foundry config doctor` checks the configuration repository, and the analysis commands live under `foundry infra analyze`.

## Configuration

### Environment not found

- **Symptom:** `[IF-CONFIG-001] Environment Not Found`.
- **Cause:** The environment name is misspelled, or the config repository is not the one you expect.
- **Fix:** Run `foundry config envs` to list the environments, check that `INFRAFOUNDRY_CONFIG_REPO` or `--config-dir` points at the right repository, and spell the name as listed.
- **Reference:** [IF-CONFIG-001](../reference/errors.md#if-config-001-environment-not-found).

### Invalid or malformed configuration

- **Symptom:** `[IF-CONFIG-002] Invalid Configuration`, often with a file name.
- **Cause:** Invalid YAML, a missing required field, or a structural mistake. An OPNsense file with a top-level `opnsense:` key and any other top-level key is rejected with "cannot mix nested 'opnsense:' format with other top-level keys". An unknown nested path or a mapping where a list belongs is also rejected, and the message names the path.
- **Fix:** Check indentation, colons and quotes in the named file. Run `foundry config doctor` for a health check of the configuration repository. For OPNsense, see [YAML Schema](../providers/opnsense.md#yaml-schema).
- **Reference:** [IF-CONFIG-002](../reference/errors.md#if-config-002-invalid-configuration).

### Environment config file missing

- **Symptom:** "Environment config not found: <path>/settings.yaml", shown as `[IF-SYSTEM-001] File Not Found`.
- **Cause:** The named environment has no `settings.yaml` under the config repository in use.
- **Fix:** Check the path in the message, create the environment with `foundry config create <name>`, or point `INFRAFOUNDRY_CONFIG_REPO` or `--config-dir` at the right repository.
- **Reference:** [IF-SYSTEM-001](../reference/errors.md#if-system-001-file-not-found).

## Selecting What to Run

### `-r` matched nothing

- **Symptom:** `[IF-VALIDATION-005] Resource Filter Matched Nothing`, "No resources matched filter: ...", followed by the available resource names.
- **Cause:** The names given with `-r` match no resource, or a `-p` package declares no resources.
- **Fix:** Check the spelling against the names listed in the message, or run `foundry infra list --env <env>`. A name that matches only some of the `-r` values prints a warning for the rest and continues.
- **Reference:** [IF-VALIDATION-005](../reference/errors.md#if-validation-005-resource-filter-matched-nothing).

### Unknown `-P` name

- **Symptom:** `Unknown provider(s): <names>. Available: <names>`.
- **Cause:** The provider name given with `-P` is not a provider that has resources in the environment.
- **Fix:** Use one of the names in `Available:`. `-P` cannot be combined with `-p` or `-r`. See [Dependency and Execution Ordering](../configuration/dependency-ordering.md#cross-provider-dependencies).

### Unsupported resource type

- **Symptom:** "Provider '<name>' does not support resource type '<type>' for resource '<resource>'. Supported types: ...", or, for an OPNsense type that the API cannot manage, "Resource '<resource>' has type '<type>', which provider 'opnsense' does not support: <reason>".
- **Cause:** The type name is wrong, or the type is one the provider rejects on purpose.
- **Fix:** Use a type from the message's list or from the provider page. For OPNsense, see [Unsupported types](../providers/opnsense.md#unsupported-types).
- **Reference:** This error is raised as a plain `ValueError`, which the catalog does not map, so the CLI shows it under `IF-GENERAL-001` and the message text identifies it. The catalog entry for the same condition is [IF-PROVIDER-003](../reference/errors.md#if-provider-003-unsupported-resource-type).

### Filtered destroy refused

- **Symptom:** `[IF-VALIDATION-006] Filtered Destroy Refused`.
- **Cause:** The filtered destroy selected Proxmox SDN zones or vnets, which would also destroy the VMs and containers that depend on them.
- **Fix:** Remove the zone or vnet from the configuration and run `foundry infra apply`. If the package has no Proxmox resources left, run `foundry infra apply --env <env> -P proxmox`.
- **Reference:** [IF-VALIDATION-006](../reference/errors.md#if-validation-006-filtered-destroy-refused).

## Locks

### Environment is locked

- **Symptom:** "Environment '<env>' is locked by <holder> since <time> (expires <time>). Use 'foundry infra unlock --env <env>' to release."
- **Cause:** Another run holds the lock, or a crashed run left one behind. A lock is auto-extended while its process runs and expires after its TTL.
- **Fix:** List locks with `foundry infra unlock --list`, then release a stale one with `foundry infra unlock --env <env>`. `--force` releases a lock that is still active and asks for confirmation unless you pass `--yes`. To wait for a lock instead of failing, use `--lock-timeout <seconds>` on `infra apply` or `infra destroy`; `--lock-ttl <seconds>` sets the stale-lock recovery time (default 600).

## Execution

### Terraform failed

- **Symptom:** `[IF-RUNNER-001] Terraform Execution Failed`.
- **Cause:** Terraform reported an error, is not installed, or lacks credentials.
- **Fix:** Read the Terraform output above the error. Run `foundry doctor` to check that Terraform or OpenTofu is installed. Inspect the generated files under `generated/<env>/terraform/<provider>/` and run `terraform init` there if needed.
- **Reference:** [IF-RUNNER-001](../reference/errors.md#if-runner-001-terraform-execution-failed).

## Credentials and Connections

### Missing or invalid credentials

- **Symptom:** `[IF-CREDENTIAL-001] Missing Credentials` or `[IF-CREDENTIAL-002] Invalid Credentials`.
- **Cause:** A required credential is not configured, has a typo, or has expired.
- **Fix:** Check the environment's `provider_settings` and its encrypted `secrets.yaml`, and the provider page for the keys it needs. Run `foundry infra doctor --env <env>`.
- **Reference:** [IF-CREDENTIAL-001](../reference/errors.md#if-credential-001-missing-credentials), [IF-CREDENTIAL-002](../reference/errors.md#if-credential-002-invalid-credentials).

### Cannot connect to, or authenticate with, an API

- **Symptom:** `[IF-API-002] Connection Failed` or `[IF-API-003] Authentication Failed`.
- **Cause:** The URL is wrong, the service is unreachable, or the key or secret is wrong or lacks permission.
- **Fix:** Verify the URL and network path, then run `foundry infra doctor --env <env> -P <provider>`, which tests connectivity and credentials per provider. For OPNsense, see [Environment variable overrides](../providers/opnsense.md#environment-variable-overrides).
- **Reference:** [IF-API-002](../reference/errors.md#if-api-002-connection-failed), [IF-API-003](../reference/errors.md#if-api-003-authentication-failed).

### SOPS decryption failed

- **Symptom:** `[IF-SECRET-002] Secret Decryption Failed`.
- **Cause:** The age key does not match the one the file was encrypted with, or `SOPS_AGE_KEY_FILE` is not set.
- **Fix:** Set `SOPS_AGE_KEY_FILE` to the right key file, and check that the file was encrypted for that key. See [Age Key Management](age-key-management.md).
- **Reference:** [IF-SECRET-002](../reference/errors.md#if-secret-002-secret-decryption-failed).

## Requirements and Dependencies

### Blueprint requirements not met

- **Symptom:** `[IF-PACKAGE-002] Blueprint Requirements Not Met`.
- **Cause:** A blueprint in scope needs Python packages or Ansible collections that are missing or at the wrong version.
- **Fix:** Run `foundry deps check --env <env>` to list them and `foundry deps sync --env <env>` to install them. `--dry-run` shows the commands first.
- **Reference:** [IF-PACKAGE-002](../reference/errors.md#if-package-002-blueprint-requirements-not-met), [IF-PACKAGE-003](../reference/errors.md#if-package-003-requirement-install-failed).

### Circular dependency

- **Symptom:** `[IF-DEPENDENCY-001] Circular Dependency Detected`, with the nodes of the cycle.
- **Cause:** Resources require each other in a loop.
- **Fix:** Inspect the graph with `foundry infra analyze graph --env <env> -f mermaid` and `foundry infra analyze dependencies --env <env>`. See [Dependency and Execution Ordering](../configuration/dependency-ordering.md#inspecting-dependencies).
- **Reference:** [IF-DEPENDENCY-001](../reference/errors.md#if-dependency-001-circular-dependency-detected).

## System

### Missing system tools

- **Symptom:** A command fails because `terraform`, `tofu`, `ansible`, `sops` or `age` cannot be found.
- **Fix:** Run `foundry doctor`. It checks that an IaC tool (Terraform or OpenTofu), Ansible, SOPS and Age are on the `PATH`.

## Per-Topic Troubleshooting

These pages have their own Troubleshooting sections:

- [CLI Reference](../usage/cli-reference.md#troubleshooting)
- [Validation and Pre-Flight Checks](../usage/validation.md#troubleshooting)
- [Settings File Structure](../configuration/settings-file-structure.md#troubleshooting)
- [Separate Config Repository](../configuration/separate-config-repo.md#troubleshooting)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md#troubleshooting)
- [Terraform Runner](../runners/terraform.md#troubleshooting) and [Ansible Runner](../runners/ansible.md#troubleshooting)
- [Drift Detection](drift-detection.md#troubleshooting) and [Drift Remediation](drift-remediation.md#troubleshooting)
- [OPNsense Provider](../providers/opnsense.md#troubleshooting)
- [Dependency and Execution Ordering](../configuration/dependency-ordering.md#troubleshooting)
