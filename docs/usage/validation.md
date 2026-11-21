---
title: "Validation and Pre-Flight Checks"
description: "The three tiers of validation that run before plan and apply"
audience:
  - users
tags:
  - usage
---

# Validation and Pre-Flight Checks

## Overview

InfraFoundry provides a three-tier validation system to catch configuration, reference, and connectivity issues before an apply, keeping deployments safe and predictable. `foundry infra doctor` runs all of it. `foundry infra plan` and `foundry infra apply` run the part of each provider's validation that needs no network, described in [Validation during plan and apply](#validation-during-plan-and-apply).

## Audience and Prerequisites

- **Audience:** Operators and CI pipelines running plan/apply workflows.
- **Prerequisites:** Config repo available, `foundry` installed via `uv`, provider credentials and network access for targeted environments.

## When to Use This

- Before any plan/apply, especially for production changes.
- After editing settings, resources, or secrets to ensure structural integrity.
- In CI to block merges when validation fails.

## Which Command When

The doctors and `infra plan` answer different questions. The doctors check that the tools, the config repo and an environment are sound. `infra plan` shows what an apply would change. None of them changes infrastructure.

| Command | Question it answers | Scope | Calls the network |
| :--- | :--- | :--- | :--- |
| `foundry doctor` | Are the tools installed? | The workstation | No |
| `foundry config doctor` | Is the config repo healthy? | The whole config repo, every environment | No provider APIs; it reads local files and the state backend |
| `foundry infra doctor --env <env>` | Is this environment's config valid against the real systems, and where do its secrets come from? | One environment, narrowed with `--provider`, `--package` or `--resource` | Yes: provider APIs, SSH to jumphosts |
| `foundry infra plan --env <env>` | What would an apply change? | One environment, narrowed with `--provider`, `--package` or `--resource` | Validation is offline; the runner's plan (for example `terraform plan`) reads live state |
| `foundry config show --env <env>` | What does the resolved config look like? | One environment | No |

`infra plan` is the only one of these that produces output for an apply: it records a deployment in the state database and, unless `--dry-run` is given, generates the files under `generated/<env>/` and runs each runner's plan.

Neither doctor prints your configuration. To see it after variable substitution, use `config show`. A scoped `infra doctor` (`--package` or `--resource`) lists where each secret reference resolves, without showing values ([Secret Sources](#secret-sources)).

Run them from the widest scope to the narrowest:

1. `foundry doctor`: after installing or upgrading tools.
2. `foundry config doctor`: after cloning or restructuring the config repo, adding an environment or changing SOPS keys.
3. `foundry infra doctor --env <env>`: after editing an environment's resources, packages or secrets.
4. `foundry infra plan --env <env>`: to review the change set.
5. `foundry infra apply --env <env>`: to make the change.

`infra plan` repeats the offline part of the provider validation that `infra doctor` runs, so a plan fails on a config error even when no doctor was run. The checks that need the network run only in `infra doctor` ([Validation during plan and apply](#validation-during-plan-and-apply)).

## Three-Tier Doctor System

InfraFoundry validation is organized into three levels, each checking a different scope:

| Level | Command | What It Checks |
|-------|---------|----------------|
| **System** | `foundry doctor` | Binary dependencies (Terraform, OpenTofu, Ansible, SOPS, Age) |
| **Config** | `foundry config doctor [--deep]` | Config repo structure, environments, state backend, SOPS keys, state/filesystem consistency, blueprint validation |
| **Infrastructure** | `foundry infra doctor --env <env>` | Provider API connectivity, OPNsense endpoint support for the box version ([details](../development/opnsense-resource-coverage.md#endpoint-registry-and-version-check-1239)), nodes/hosts, storage pools, network bridges, templates, resource IDs, MAC conflicts, and the jumphost of packages that set one |

## Quick Start

```bash
# Check system dependencies
foundry doctor

# Check config repo health
foundry config doctor --deep

# Validate against provider APIs
foundry infra doctor --env dev
foundry infra doctor --env dev --resource vm-01 --resource vm-02
foundry infra doctor --env prod --package k3s-cluster
foundry infra doctor --env dev --provider opnsense   # only OPNsense; repeat -P for more
foundry infra doctor --env dev --verbose
```

## Jumphost Preflight

A package that sets `jumphost` runs its blueprint scripts on that host, and the scripts SSH to the package's VMs with the jumphost's own ssh-agent. If the agent holds no key, or not the one the VMs accept, the apply only fails minutes later, after terraform has created the VMs. `infra doctor` checks the jumphost first, once per jumphost, in a single SSH session opened the same way the script handler opens it:

```
Jumphost preflight (ansible@ansible.example.net):
  [OK] SSH to jumphost
  [OK] ssh-agent: 1 key(s) loaded
  [SKIP] key match: package declares no public key to compare
  [OK] tools: rsync, bash, python3, ssh, scp
  [OK] writable /tmp
  [OK] target k3s-server (192.0.2.70): not deployed; routable and unused
  [OK] target k3s-agent-1 (192.0.2.71): not deployed; routable and unused
  [OK] target k3s-agent-2 (192.0.2.72): not deployed; routable and unused
  [OK] target k3s-agent-3 (192.0.2.73): not deployed; routable and unused
  [OK] output ~/.kube/k3s-demolab.yaml: exists, writable
Jumphost preflight: 9 OK, 1 SKIP
```

| Check | Fails when |
|-------|-----------|
| SSH to jumphost | The jumphost can't be reached non-interactively (BatchMode), or its host key is not in your `known_hosts`. The remaining checks are skipped. |
| ssh-agent | `ssh-add -l` finds no keys (exit 1) or no agent (exit 2). |
| key match | A public key the package declares (`ssh_public_key`, or a VM's `ssh_keys`) is not in the agent. Comments are ignored. `SKIP` when the package declares none, for example when the key comes from a cloud-init snippet. |
| tools | `rsync`, `bash`, `python3`, `ssh` or `scp` is missing on the jumphost. |
| writable /tmp | The script handler can't create its work directory in `/tmp`. |
| target (deployed) | SSH from the jumphost to the VM fails, including a host key that differs from the pinned one. `SKIP` when the package pinned no key. The detail carries ssh's last error line, such as `Permission denied (publickey)`. |
| target (not deployed) | The jumphost has no route to the IP, or something already answers a ping there, which means another host holds the address. `WARN` when `ip` is missing on the jumphost. |
| output | Only `WARN`: an `outputs:` destination doesn't render, isn't absolute, or can't be written on the workstation. An apply only warns about these too. |

**Targets** are the package's VMs that have a DHCP reservation whose `hostname` is the VM name; the reservation gives the IP. A VM counts as deployed when its newest state-DB row, ignoring the `planned` rows `infra plan` adds for resources not yet deployed, is `active` or `updating`; `deleted` or no row means not deployed, and anything in between is `SKIP`. Target SSH runs as the package's `ssh_user`, else the user in `jumphost`, strictly, against the host key the package pinned in `ssh_known_hosts` (staged in a temporary file on the jumphost, looked up by VM name). A deployed VM with no pinned key is `SKIP` with a `foundry secrets host-keys --env <env>` hint. The SSH hop to the jumphost itself is strict against your own `known_hosts`; see [SSH Host Key Checking](../guides/ssh-host-key-checking.md).

A scoped doctor run (`-p`, `-r`, `-P`) reports only on the selected resources and resolves names such as compartments, VCNs, vswitches and interfaces against all of the provider's resources in the environment, so a reference to something another package defines is not flagged.

Any `FAIL` makes doctor exit 1, so `foundry infra doctor --env prod -p k3s-cluster && foundry infra apply --env prod -p k3s-cluster` stops before the apply.

## Secret Sources

With `-p/--package` or `-r/--resource`, `infra doctor` also lists where each secret reference of the in-scope resources resolves from. An unscoped run, or one limited with `-P`, does not print it.

```text
Secret sources (package example-app):
  ✓ example-app terraform_secrets[0] package.admin_token -> envs/prod/apps/example-app/secrets.yaml
  ✓ example-app terraform_secrets[1] db.password -> envs/prod/secrets.yaml
  - example-app terraform_secrets[2] outputs.opnsense.api_key -> outputs of opnsense (apply time)
  ✗ example-app terraform_secrets[3] db.missing -> envs/prod/secrets.yaml: Resource 'example-app' references unknown secret key 'db.missing'. Ensure each dotted path exists in the env's secrets file.
Secret sources: 2 resolved, 1 at apply time, 1 unresolved
```

| Reference | Source | Status |
| --- | --- | --- |
| `package.<key>` | `secrets.yaml` of the package that defines the resource | `✓` when the key exists, else `✗` with the reason |
| `outputs.<provider>.<output>` | Terraform outputs of that provider | `-` at apply time when well formed, else `✗` |
| anything else | the environment's `secrets.yaml` | `✓` when the dotted path exists, else `✗` |

**Field paths** name where the reference sits: `terraform_secrets[<i>]`, and for Kubernetes `string_data_secrets.<KEY>`, `data_secrets.<KEY>` and `set_sensitive[<i>].value_secret` (`<i>` counts every `set_sensitive` entry, literal ones included). A malformed field shows as one `✗` row with the reason.

Any `✗` makes doctor exit 1. Only references and paths are shown, never secret values. With `--format json` stdout holds one document (`environment`, `passed`, `providers`, `secret_sources`) and the text report goes to stderr.

## Validation during plan and apply

`foundry infra plan`, and so `foundry infra apply`, runs each provider's offline validation (`validate_offline`) first, as one pass over every provider in scope. It runs after the provider and resource filters and the policy check, and before any `before_plan` hook, state write or runner call.

- **Warnings** are printed under `Config validation: <provider>` and the plan continues.
- **Errors** print the report and stop the plan with [IF-VALIDATION-007](../reference/errors.md#if-validation-007-configuration-validation-failed). The deployment is marked failed and no change set is computed. `apply` stops before it changes anything.
- `-P`, `-r` and `-p` are honoured: only the selected resources are checked, and references still resolve against all of the provider's resources.
- `--dry-run` runs the check too, so a dry run shows the errors a real plan would hit.
- A validator that crashes adds a warning naming the provider, and the plan continues.

Checks that need the network stay in `infra doctor`. Rollback and destroy do not run this pass.

| Provider | Checked on plan and apply | Doctor only |
| :--- | :--- | :--- |
| `opnsense` | Every validator that does not read live state (Unbound, Kea, interface, syslog and HA sync settings, source NAT, cron, trust, OpenVPN, categories, ACME, Tailscale, Monit, system, resource names, virtual IP VHID reuse and CARP subnet membership) | Aliases, interfaces, gateways and Unbound overrides read from the API; firewall rule, VLAN, assignment, NAT, gateway, route, virtual IP, host alias, host discovery and radvd checks that use them; HA sync interface and sync items; CARP VIP state and HA peer reachability; endpoint support (the runner's plan checks it) |
| `proxmox` | Tailscale schema, `terraform_secrets` references | Nodes, storage, bridges, templates and VMIDs from the cluster |
| `oci` | Local cross-references, Tailscale schema, `terraform_secrets` references | OCI API checks |
| `host` | Host schema, `terraform_secrets` references | SSH reachability (a host created earlier in the same apply cannot be reached at plan time) |
| `aws`, `esxi`, `tailscale` | All reference checks (none use the network) | Connectivity |

| `kubernetes` | Local cross-references (configmaps, secrets, namespaces, service accounts, service selectors), secret `data` base64, `terraform_secrets` references, Helm `chart` and `repository` | Kubeconfig and API connectivity; namespaces and CRD groups in the cluster |

A kubeconfig that does not exist yet (a cluster created in the same apply) gives a warning and skips the cluster checks.

See [ADR-0023](../decisions/0023-infra-plan-runs-providers-offline-validation-live-checks-stay-in-infra-doctor.md) and [Implementing providers: validate_offline()](../development/implementing-providers.md#validate_offline).

## Additional Validation Commands

Beyond the doctor commands, InfraFoundry offers additional validation tools:

- **`foundry infra test --env <env>`** -- Run infrastructure tests against configurations (duplicate names, missing references, configuration problems).
- **`foundry infra security --env <env>`** -- Scan generated Terraform/Ansible for security issues using Checkov.
- **`foundry infra analyze dependencies --env <env>`** -- Verify dependency graph is acyclic and references resolve.

## Examples

- **Pre-deployment validation:**
  ```bash
  foundry config doctor --deep
  foundry infra doctor --env prod
  foundry infra test --env prod
  ```
- **CI usage (GitHub Actions excerpt):**
  ```yaml
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        - run: foundry config doctor --deep
        - run: foundry infra doctor --env prod
        - run: foundry infra test --env prod
  ```

## Related Documentation

- [CLI Reference](cli-reference.md)
- [Settings File Structure](../configuration/settings-file-structure.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [State Management](../architecture/state-management.md)

## Troubleshooting

- **Symptom:** Missing templates/networks in doctor output. **Fix:** Create the resource in the provider or update the configuration reference; rerun `foundry infra doctor --env <env>`.
- **Symptom:** Doctor reports API failures. **Fix:** Verify endpoints, tokens, kubeconfig, and network reachability; test with provider CLIs.
- **Symptom:** `[FAIL] ssh-agent: agent is running but has no keys loaded`. **Fix:** On the jumphost, load the key the VMs accept into the agent the jumphost user's non-interactive SSH sessions use (for example with `ssh-add` or keychain), then rerun doctor.
- **Symptom:** `Host key verification failed` or a `No ED25519 host key is known for ...` line for the jumphost or a target. **Fix:** Record the key in your `known_hosts` after checking its fingerprint, or pin the VM key with `foundry secrets host-keys --env <env>`. See [SSH Host Key Checking](../guides/ssh-host-key-checking.md).
- **Symptom:** Unknown resource/provider. **Fix:** Confirm resource type spelling and provider availability in the current framework version.

---

Last updated: 2026-04-13 GMT


---
[Back to Table of Contents](../index.md)
