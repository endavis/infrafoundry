---
title: "OPNsense Provider"
description: "Manage an OPNsense firewall through the direct API: credentials, YAML schema, resource types, apply order, deletes, migration and validation"
audience:
  - users
tags:
  - providers
---

# OPNsense Provider

The OPNsense provider manages a firewall through the OPNsense API. You describe VLANs, interface assignments, firewall rules, DNS, DHCP, certificates, VPN, monitoring and more in YAML, and `foundry infra plan` and `foundry infra apply` reconcile the box against it.

This page is the user entry point. Per-type field detail lives in [OPNsense Resource Coverage](../development/opnsense-resource-coverage.md).

## Overview

Every resource type runs through the direct-API runner, `OPNsenseDirectRunner` ([ADR-0014](../decisions/0014-opnsense-direct-api-apply-mechanism.md), [ADR-0015](../decisions/0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md)). There is no second, Terraform-based way to manage a resource. The provider's Terraform output is only scaffolding: the backend, provider and variables files and an outputs block, with no resource blocks (`OPNsenseProvider.generate_terraform`, and `get_terraform_resource_types()` returns an empty mapping).

The runner reads your YAML at run time, compares it with the live box and issues the API calls for the difference.

## Audience and Prerequisites

- **Audience:** Operators who manage an OPNsense firewall as code.
- **Prerequisites:** An OPNsense API key and secret, network access to the API, an environment set up with `foundry config create <name>` and, for `interfaces.assignments`, SSH key access to the firewall.

## When to Use This

- Declaring the firewall configuration in a config repo instead of in the GUI.
- Bringing an existing firewall under management in steps with `config migrate` and `--add-only`.
- Moving a configuration from one firewall to another.

## Quick Start

1. Add the provider settings to the environment's `settings.yaml` (see [Provider Settings and Credentials](#provider-settings-and-credentials)).
2. Write resources under `envs/<env>/opnsense/` or `envs/<env>/resources/` (see [YAML Schema](#yaml-schema)).
3. Check, plan and apply:

```bash
foundry infra doctor --env <env> -P opnsense
foundry infra plan --env <env> -P opnsense
foundry infra apply --env <env> -P opnsense
```

## Provider Settings and Credentials

The provider reads its settings from `provider_settings.opnsense` in the environment's `settings.yaml`:

```yaml
name: test

providers:
  - opnsense

provider_settings:
  opnsense:
    api_url: https://fw-test.example.com
    api_key: secret://env_secrets/opnsense/api_key
    api_secret: secret://env_secrets/opnsense/api_secret
    verify_ssl: true
```

| Key | Default | Meaning |
|-----|---------|---------|
| `api_url` | empty | Base URL of the firewall |
| `api_key` | empty | API key |
| `api_secret` | empty | API secret |
| `verify_ssl` | `true` | Verify the TLS certificate |
| `proxy` | unset | Proxy for API calls, for example a SOCKS proxy |
| `ssh_host` | host of `api_url` | SSH host for the interface-assignments controller install |
| `ssh_user` | `root` | SSH user for that install |
| `ssh_port` | `22` | SSH port for that install |
| `ssh_key` | ssh-agent or `~/.ssh/config` | Private key path for that install |

Keep the key and secret in the environment's SOPS-encrypted `secrets.yaml` and reference them with `secret://` URIs.

### SSH is needed for interface assignments only

`interfaces.assignments` writes need a one-time controller install on the firewall over SSH. Only a run that has an assignment to write does this. A run with no assignment changes, and every other type, needs the API alone. The SSH login uses key authentication only (an ssh-agent or `~/.ssh/config`); there is no password support. If no SSH host resolves, the run stops with a message naming `ssh_host` and `api_url`.

### Environment variable overrides

Each credential can be overridden by an `OPNSENSE_*` environment variable (`OPNSENSE_API_URL`, `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET`, `OPNSENSE_VERIFY_SSL`, `OPNSENSE_PROXY`). They apply **only** when `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE` is set to a truthy value; otherwise they are ignored, so a forgotten exported variable cannot redirect a run. When an override changes the URL, the run logs a one-time warning that names the resolved URL. `OPNSENSE_SSH_USER`, `OPNSENSE_SSH_PORT` and `OPNSENSE_SSH_KEY` are always read, while `OPNSENSE_SSH_HOST` follows the same gate. See [Per-Environment Credentials](../configuration/per-environment-credentials.md) and [Settings File Structure](../configuration/settings-file-structure.md).

## YAML Schema

The schema is nested under a top-level `opnsense:` key and mirrors the OPNsense API path tree ([ADR-0016](../decisions/0016-direct-opnsense-nested-yaml-schema.md)). The dotted path to a leaf is the resource type, for example `firewall.aliases`.

```yaml
# envs/<env>/opnsense/<file>.yaml
opnsense:
  firewall:
    aliases:                       # a list: a YAML sequence of entries
      - name: trusted-hosts
        config:
          name: trusted-hosts
          type: host
          content:
            - 192.0.2.10
            - 192.0.2.11
          description: Hosts allowed to reach the admin network
  unbound:
    settings:                      # a singleton: a mapping
      general:
        enabled: true
        regdhcp: true
      advanced:
        hideidentity: true
        prefetch: true
```

The rules the loader applies (`PackageLoader._parse_nested_provider_format`):

- **Where files go.** Under `envs/<env>/opnsense/` (provider-centric) or `envs/<env>/resources/` (resource-centric). Both loaders accept the nested form.
- **One format per file.** A file with a top-level `opnsense:` mapping cannot have any other top-level key. Mixing raises `InvalidConfigurationError`.
- **Lists.** A list type is a sequence of entries, and each entry needs a `name:`.
- **Singletons.** A singleton type is a mapping. Its resource name is its dotted path (`unbound.settings`), so several singletons can coexist and each can be targeted with `-r`.
- **Mistakes are errors.** A mapping where a list belongs (or the reverse) and an unknown dotted path both raise an error that names the path.

### Cross-references

A field that refers to another resource accepts three forms (`providers/opnsense/validators/_xref.py`, [ADR-0016](../decisions/0016-direct-opnsense-nested-yaml-schema.md#cross-reference-syntax)):

| Form | Meaning |
|------|---------|
| `<name>` | A bare name, looked up in the type the field expects |
| `<sub>.<name>` | Relative to the current plugin, for example `accounts.my-account` |
| `<plugin>.<sub>.<name>` | An absolute path across plugins, for example `cron.jobs.my-job` |

## Resource Type Catalog

These are the types the provider accepts, in the dotted form you use under `opnsense:`. The groups link to the section of [OPNsense Resource Coverage](../development/opnsense-resource-coverage.md) that holds the field detail. The [coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) lists every type with its status.

| Group | Types | Detail |
|-------|-------|--------|
| System | `system.firmware`, `system.tuning`, `system.users`, `system.groups` | [Coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) |
| Interfaces | `interfaces.settings`, `interfaces.vlans`, `interfaces.assignments`, `interfaces.virtual_ips` | [Interface settings](../development/opnsense-resource-coverage.md#interface-settings-1092) |
| Syslog | `syslog.settings` | [Syslog settings](../development/opnsense-resource-coverage.md#syslog-settings-804) |
| Firewall | `firewall.aliases`, `firewall.source_nat`, `firewall.nat`, `firewall.rules`, `firewall.categories` | [Outbound NAT mode](../development/opnsense-resource-coverage.md#outbound-nat-mode-1333), [Firewall categories](../development/opnsense-resource-coverage.md#firewall-categories-1286) |
| Routing | `routing.gateways`, `routing.static` | [Coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) |
| Unbound DNS | `unbound.host_overrides`, `unbound.host_aliases`, `unbound.forwards`, `unbound.advanced`, `unbound.settings` | [Unbound advanced settings](../development/opnsense-resource-coverage.md#unbound-advanced-settings-1254), [Unbound general and advanced settings](../development/opnsense-resource-coverage.md#unbound-general-and-advanced-settings-1091) |
| Kea DHCP | `kea.dhcp4.subnets`, `kea.dhcp4.reservations`, `kea.dhcp6.subnets`, `kea.dhcp6.reservations` | [ISC to Kea migration](../guides/isc-to-kea-migration.md) |
| Router advertisements | `radvd` | [Coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) |
| Cron | `cron.jobs` | [Coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) |
| Trust store | `trust.cas`, `trust.certs` | [Trust CAs and certificates](../development/opnsense-resource-coverage.md#trust-cas-and-certificates-807) |
| OpenVPN | `openvpn.static_keys`, `openvpn.instances` | [OpenVPN client instances](../development/opnsense-resource-coverage.md#openvpn-client-instances-808), [OpenVPN static keys](../development/opnsense-resource-coverage.md#openvpn-static-keys-1319) |
| Host discovery | `hostdiscovery` | [Host discovery](../development/opnsense-resource-coverage.md#host-discovery-792) |
| ACME client | `acmeclient.settings`, `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions`, `acmeclient.certs` | [ACME client](../development/opnsense-resource-coverage.md#acme-client-790) |
| Tailscale (node side) | `tailscale.settings`, `tailscale.auth`, `tailscale.subnets` | [Tailscale](../development/opnsense-resource-coverage.md#tailscale-787) |
| Monit | `monit.settings`, `monit.alerts`, `monit.tests`, `monit.services` | [Monit](../development/opnsense-resource-coverage.md#monit-791) |

The `tailscale.*` types configure the `os-tailscale` plugin on the firewall. The [Tailscale provider](tailscale.md) manages the tailnet control plane, which is a separate provider.

### Unsupported types

These types are accepted by the YAML loader, but `infra plan` and `infra apply` reject them with a reason (`OPNsenseProvider.UNSUPPORTED_RESOURCE_TYPES`, checked by `Orchestrator.validate_resources`), because their endpoints do not exist on OPNsense 26.1:

| Type | Where to configure it instead |
|------|-------------------------------|
| `system.hostname` | System > Settings > General in the GUI |
| `system.dns` | System > Settings > General in the GUI |
| `system.ssh` | System > Settings > Administration in the GUI |
| `system.webgui` | System > Settings > Administration in the GUI |
| `system.remotebackup` | System > Configuration > Backups in the GUI |

`firewall.log` is also accepted by the loader but is not a supported type. Do not use it.

## Apply Order and Deletes

Types are applied in the order of the provider's dispatch table (`OPNsenseProvider.get_direct_api_resource_types`), which follows dependencies: system types first, then interfaces, aliases, NAT, gateways and routes, rules, DNS, DHCP, trust, OpenVPN, host discovery, ACME, Tailscale and monit. Gateways and static routes are applied before the firewall rules that name them, aliases before the rules and NAT entries that use them, and a Kea subnet before its reservations.

Deletes are split into their own phase for every type that depends on another: the runner deletes children before parents, in reverse table order, and then applies adds and updates in table order. The phase exists because OPNsense refuses to delete, for example, a VLAN that is still assigned ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)).

Deletes are limited to the **managed set**: the runner deletes only objects InfraFoundry itself applied, never an object that was on the box before. See [How deletes work](../development/opnsense-resource-coverage.md#how-deletes-work-the-managed-set-1256) for the rules per type.

## Adding Without Deleting with `--add-only`

`foundry infra plan` and `foundry infra apply` take `--add-only`. It suppresses deletes for live resources that are not in your YAML, which suits a partial migration where the YAML does not yet describe everything on the box. Only OPNsense direct-API resources honour it; other runners accept the flag and ignore it. It is implied for OPNsense resources when `-r` or `-p` filters the run.

## Migrating an Existing Firewall

`foundry config migrate` reads the live configuration through the API and writes InfraFoundry YAML:

```bash
foundry config migrate --env <env> --provider opnsense --component firewall.aliases --dry-run
foundry config migrate --env <env> --provider opnsense --component firewall.aliases
```

| Flag | Meaning |
|------|---------|
| `-e`, `--env` | Environment name (required) |
| `-p`, `--provider` | Provider name (required) |
| `-c`, `--component` | Component to migrate (required) |
| `-i`, `--interfaces` | Specific interfaces to migrate, repeatable |
| `-o`, `--output` | Output file; defaults to `envs/{env}/resources/migrated-{component}.yaml` |
| `--dry-run` | Show what would be generated without writing files |

The component is the extractor key the provider registers, not always the same as a resource type. The keys are `acmeclient.accounts`, `acmeclient.actions`, `acmeclient.certs`, `acmeclient.settings`, `acmeclient.validations`, `cron.jobs`, `firewall.aliases`, `firewall.categories`, `firewall.nat`, `firewall.rules`, `firewall.source_nat`, `hostdiscovery`, `interfaces.assignments`, `interfaces.settings`, `interfaces.virtual_ips`, `interfaces.vlans`, `isc_to_kea`, `kea_dhcp`, `monit.alerts`, `monit.services`, `monit.settings`, `monit.tests`, `routing.gateways`, `routing.static`, `syslog.settings`, `tailscale.auth`, `tailscale.settings`, `tailscale.subnets`, `unbound.forwards`, `unbound.host_aliases`, `unbound.host_overrides` and `unbound.settings`. An unknown component is refused with this list.

!!! note "The command's own help example"
    The `--help` text of `config migrate` shows `--component vlans`. The registered key is `interfaces.vlans`, and `vlans` is refused as an unsupported component.

After a migration, plan and apply with `--add-only` until the YAML describes the whole box. For the ISC DHCP to Kea conversion see [ISC to Kea Migration](../guides/isc-to-kea-migration.md). For moving a configuration to a new firewall see the [box-to-box runbook](../development/opnsense-resource-coverage.md#box-to-box-migration-runbook-template).

## Finalization Hooks

After an apply, the runner makes one reconfigure call per service whose components changed, however many of its types changed. The hook keys (`OPNsenseProvider.get_finalization_hooks`) are `kea_reconfigure`, `unbound_reconfigure`, `radvd_reconfigure`, `cron_reconfigure`, `openvpn_reconfigure`, `tunables_reconfigure`, `interfaces_settings_reconfigure`, `syslog_reconfigure`, `source_nat_apply`, `hostdiscovery_reconfigure`, `acmeclient_reconfigure`, `tailscale_reconfigure` and `monit_reconfigure`. A hook that fails fails the apply.

## Endpoint and Version Check

During `infra plan` (and so `infra apply`) and `infra doctor`, the box's OPNsense version is read and each type's endpoints are checked against it (`check_endpoint_support`). A type whose endpoints that version lacks is reported as an error, and an unreadable setting or unknown version is reported as a warning. See [Endpoint registry and version check](../development/opnsense-resource-coverage.md#endpoint-registry-and-version-check-1239).

## Validation and Checks

```bash
foundry infra doctor --env <env> -P opnsense
```

The check tests connectivity to the API (`validate_connectivity`), that referenced OPNsense resources exist, and the endpoint support described above (`validate_references`).

## Examples

A plan that touches only OPNsense, without deleting anything the YAML omits:

```bash
foundry infra plan --env <env> -P opnsense --add-only
```

A plan for one resource by name:

```bash
foundry infra plan --env <env> -r trusted-hosts
```

## Related Documentation

- [OPNsense Resource Coverage](../development/opnsense-resource-coverage.md)
- [Dependency and Execution Ordering](../configuration/dependency-ordering.md)
- [ADR-0014: Direct-API Apply](../decisions/0014-opnsense-direct-api-apply-mechanism.md)
- [ADR-0016: Nested YAML Schema](../decisions/0016-direct-opnsense-nested-yaml-schema.md)
- [ADR-0018: Managed-Set Deletes](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)
- [Tailscale Provider](tailscale.md)

## Troubleshooting

- **A plugin-backed type fails because the plugin is missing.** See the "Plugin not installed" subsections of [ACME client](../development/opnsense-resource-coverage.md#acme-client-790) and [Tailscale](../development/opnsense-resource-coverage.md#tailscale-787) in the coverage document. `system.firmware` installs the plugins.
- **Connection or authentication errors.** See [IF-API-002](../reference/errors.md#if-api-002-connection-failed) and [IF-API-003](../reference/errors.md#if-api-003-authentication-failed), and run `foundry infra doctor --env <env> -P opnsense`.
- **Unsupported resource type.** See [Unsupported types](#unsupported-types).
- **Anything else.** See [Troubleshooting Common Errors](../guides/troubleshooting.md).
