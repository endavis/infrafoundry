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
| `ha_sync_after_apply` | `true` | Sync the config to the HA backup after an apply: `true` (only when the apply changed something), `"always"`, or `false` |
| `ha_sync_timeout` | `300` | Seconds to wait for each HA sync call, an integer above 0 |

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
| High availability | `hasync.settings` | [HA sync settings](../development/opnsense-resource-coverage.md#ha-sync-settings-1389) |
| Syslog | `syslog.settings` | [Syslog settings](../development/opnsense-resource-coverage.md#syslog-settings-804) |
| Firewall | `firewall.aliases`, `firewall.source_nat`, `firewall.nat`, `firewall.rules`, `firewall.categories` | [Outbound NAT mode](../development/opnsense-resource-coverage.md#outbound-nat-mode-1333), [Firewall categories](../development/opnsense-resource-coverage.md#firewall-categories-1286) |
| Routing | `routing.gateways`, `routing.static` | [Coverage matrix](../development/opnsense-resource-coverage.md#coverage-matrix) |
| Unbound DNS | `unbound.host_overrides`, `unbound.host_aliases`, `unbound.forwards`, `unbound.advanced`, `unbound.settings` | [Unbound advanced settings](../development/opnsense-resource-coverage.md#unbound-advanced-settings-1254), [Unbound general and advanced settings](../development/opnsense-resource-coverage.md#unbound-general-and-advanced-settings-1091) |
| Kea DHCP | `kea.dhcp4.subnets`, `kea.dhcp4.reservations`, `kea.dhcp4.ha`, `kea.dhcp4.ha_peers`, `kea.dhcp6.subnets`, `kea.dhcp6.reservations` | [ISC to Kea migration](../guides/isc-to-kea-migration.md), [Kea DHCPv4 high availability](../development/opnsense-resource-coverage.md#kea-dhcpv4-high-availability-1392) |
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

The component is the extractor key the provider registers, not always the same as a resource type. The keys are `acmeclient.accounts`, `acmeclient.actions`, `acmeclient.certs`, `acmeclient.settings`, `acmeclient.validations`, `cron.jobs`, `firewall.aliases`, `firewall.categories`, `firewall.nat`, `firewall.rules`, `firewall.source_nat`, `hasync.settings`, `hostdiscovery`, `interfaces.assignments`, `interfaces.settings`, `interfaces.virtual_ips`, `interfaces.vlans`, `isc_to_kea`, `kea.dhcp4.ha`, `kea.dhcp4.ha_peers`, `kea_dhcp`, `monit.alerts`, `monit.services`, `monit.settings`, `monit.tests`, `routing.gateways`, `routing.static`, `syslog.settings`, `tailscale.auth`, `tailscale.settings`, `tailscale.subnets`, `unbound.forwards`, `unbound.host_aliases`, `unbound.host_overrides` and `unbound.settings`. An unknown component is refused with this list.

!!! note "The command's own help example"
    The `--help` text of `config migrate` shows `--component vlans`. The registered key is `interfaces.vlans`, and `vlans` is refused as an unsupported component.

After a migration, plan and apply with `--add-only` until the YAML describes the whole box. For the ISC DHCP to Kea conversion see [ISC to Kea Migration](../guides/isc-to-kea-migration.md). For moving a configuration to a new firewall see the [box-to-box runbook](../development/opnsense-resource-coverage.md#box-to-box-migration-runbook-template).

## Finalization Hooks

After an apply, the runner makes one reconfigure call per service whose components changed, however many of its types changed. The hook keys (`OPNsenseProvider.get_finalization_hooks`) are `kea_reconfigure`, `unbound_reconfigure`, `radvd_reconfigure`, `cron_reconfigure`, `openvpn_reconfigure`, `tunables_reconfigure`, `interfaces_settings_reconfigure`, `syslog_reconfigure`, `hasync_reconfigure`, `source_nat_apply`, `hostdiscovery_reconfigure`, `acmeclient_reconfigure`, `tailscale_reconfigure` and `monit_reconfigure`. A hook that fails fails the apply.

## HA Sync After Apply

When the firewall is the primary of an HA pair, an apply also has to push the config to the backup. After every component has applied and the finalization hooks have run, the provider reads `synchronize_to_ip` from the live `core/hasync/get`. If a backup is set, it calls `core/hasync_status/version` as a preflight and then `core/hasync_status/restartAll`, the action behind the GUI's "Synchronize and reconfigure all". It runs after a successful `apply` and after a successful `destroy` (#1442), where `changed` is true when something was deleted, so the backup loses the removed resources too. It does not run on `plan` or after a failed component. It runs after the `hasync.settings` reconfigure, so an apply that sets `synchronize_to_ip` for the first time syncs to the new target.

`ha_sync_after_apply` controls it:

| Value | Meaning |
|-------|---------|
| `true` (default) | Sync only when the apply created, updated or deleted something. A no-op apply restarts nothing on the backup, unless the node sets `ha_backup` and the backup lacks one of its CARP VIPs (see below). |
| `"always"` | Sync even when nothing changed. |
| `false` | Never sync. |

`ha_sync_timeout` (default `300` seconds) applies to all three calls. An unreachable backup makes the preflight answer only after about 60 seconds, so the 30 second client default would hide the endpoint's message. With `true`, a no-op apply on a node that sets `ha_backup` (see the firewalls table below) makes one more check. It reads the CARP VIPs of this node and of the `ha_backup` firewall, using `ha_sync_timeout` for both reads, and matches them on `(vhid, subnet)`. If the backup lacks any VIP the primary has, for example because the backup was rebuilt, the apply syncs as if something had changed. A VIP only the backup has does not trigger a sync. Without `ha_backup` the check does not run, and `"always"`, `false` and an apply that changed something behave as before. A bad value for either key fails `infra plan` and `infra apply` before anything is written.

The apply prints one status line, or one of these skips:

- `HA sync after apply disabled (ha_sync_after_apply: false)`
- `HA sync skipped: nothing changed`
- `HA sync skipped: no synchronize_to_ip on this node`
- `HA sync skipped: nothing changed, backup <name> has all N CARP VIP(s)`
- `HA sync skipped: nothing changed, no CARP VIPs on this node to compare with backup <name>`
- `HA sync skipped: nothing changed, could not read CARP state of ha_backup firewall '<name>': <error>`

When the check finds missing VIPs, the status line reads `HA sync to backup <ip>: backup <name> missing M of N CARP VIP(s), synchronized and reconfigured K service(s)`.

When the preflight or the sync fails, the apply fails with an error that names the backup address and the endpoint and quotes the endpoint's message, for example `HA sync to backup 192.0.2.2 failed at core/hasync_status/version: <message>`. A timeout or connection error names the backup, the endpoint and `ha_sync_timeout`.

**State after a failure.** The primary has already been written, so the next apply sees no difference on the primary. With the default `true`, it syncs only when the node sets `ha_backup` and the backup still lacks a CARP VIP of the primary, so a failed sync to a rebuilt backup retries on the next apply. Without `ha_backup`, or when the backup already has every VIP, apply once with `ha_sync_after_apply: "always"` to retry, then set it back.

!!! warning "Errors while pushing the config are not reported"
    OPNsense's `exec_sync` always answers `{"status": "done"}`, so a failure while pushing the config to the backup is not visible to InfraFoundry. A successful apply means the endpoints answered `ok`, not that the backup holds the config. Check the backup after the first sync.

## Several firewalls per environment

One environment can manage more than one firewall, for example an HA pair or two independent firewalls. List them under `firewalls:` and name the primary:

```yaml
provider_settings:
  opnsense:
    verify_ssl: true            # shared default; an entry may override it
    primary: fw-a
    firewalls:
      fw-a:
        api_url: https://fw-a.example.com
        api_key: secret://env_secrets/opnsense/fw_a_key
        api_secret: secret://env_secrets/opnsense/fw_a_secret
        ha_backup: fw-b         # compare CARP state with fw-b in `infra doctor`; also re-sync it when it lacks a CARP VIP
      fw-b:
        api_url: https://fw-b.example.com
        api_key: secret://env_secrets/opnsense/fw_b_key
        api_secret: secret://env_secrets/opnsense/fw_b_secret
        ha_sync_after_apply: false
```

| Key | Meaning |
|-----|---------|
| `firewalls` | Map of firewall name to its settings: `api_url`, `api_key`, `api_secret`, `ssh_*`, `verify_ssl`, `proxy`, `ha_sync_after_apply`, `ha_sync_timeout` and `ha_backup` (the firewall whose CARP state `infra doctor` compares, and whose missing CARP VIPs trigger an HA sync after a no-op apply) |
| `primary` | Name of the primary firewall. Required with more than one entry |
| `ha_backup` | On an entry: the firewall that is its HA backup. Enables the CARP pair check in `infra doctor` |

Top-level `verify_ssl`, `proxy`, `ssh_user`, `ssh_port`, `ssh_key`, `ha_sync_after_apply` and `ha_sync_timeout` are shared defaults; an entry overrides them. Combining `firewalls:` with a top-level `api_url`, `api_key`, `api_secret` or `ssh_host` is an error, and so is a `primary` or `ha_backup` that names no entry. Firewall names are lowercase letters, digits and `-`, 1 to 32 characters. The flat shape above is unchanged and means one unnamed firewall.

**Which firewall a resource goes to.** The most specific selection wins:

1. a `firewall:` key on the entry (in a list entry, or on a resource-centric item);
2. a top-level `firewall:` beside `opnsense:` in the file;
3. `firewall:` in the package's `infrafoundry.yml`;
4. the primary.

```yaml
# envs/<env>/opnsense/fw-b-settings.yaml
firewall: fw-b
opnsense:
  hasync:
    settings:
      synchronize_to_ip: 192.0.2.1
```

Settings that exist once per node (`hasync.settings`, `interfaces.assignments`, interface addresses) go in a file or package with `firewall: fw-b` and, for the primary, in a default one. Resources that OPNsense carries to the backup through HA sync default to the primary. To switch HA sync off on a node, declare `reset: true` in its `hasync.settings`; removing the block does not reset it. See [HA sync settings](../development/opnsense-resource-coverage.md#ha-sync-settings-1389).

**Each firewall is its own provider.** The primary keeps the provider id `opnsense`; every other firewall is `opnsense@<name>`. So a resource name can repeat on two firewalls (`lan` on both), but twice on one firewall is still a duplicate. The managed set and deletes are per firewall, the HA sync runs once per firewall, and checks such as CARP `vhid` reuse see only that firewall's resources. Firewalls apply one after another: the primary first, then the others (the reverse on destroy). Turning a flat configuration into a `firewalls:` map keeps its state: the primary's rows stay under `opnsense`. The rows of another firewall are under `opnsense@<name>`, so `state list --provider opnsense` lists the primary only. Each firewall also gets its own generated directory (`generated/<env>/terraform/opnsense@<name>/`; the primary keeps `opnsense/`) and its own local Terraform state, and all firewalls render from the same OPNsense templates.

**Selecting firewalls on the command line.** `infra plan`, `apply`, `destroy` and `doctor` take a repeatable `--firewall <name>`. `-P opnsense` selects every firewall that has resources. `--firewall` cannot be combined with `-p` or `-r`.

```bash
foundry infra apply --env <env> --firewall fw-b
```

**Output.** With `firewalls:` declared, runner lines read `opnsense_direct[fw-b]: ...` and `plan` and `doctor` messages start with `[fw-b] `. A flat configuration prints as before.

**Environment overrides apply to the primary only.** `OPNSENSE_*` variables do not redirect the other firewalls; with `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE` set, a warning says they are ignored for them.

**CARP pair check.** With `ha_backup: fw-b` on `fw-a`, `infra doctor` also reads the CARP state on `fw-b` through its own credentials and compares every VIP by `vhid` and subnet. MASTER on `fw-a` and BACKUP on `fw-b` passes. A VIP missing on `fw-b`, MASTER on both nodes, or any other state is an error. If `fw-b` cannot be read the result is a warning. The per-node CARP health check still runs for each firewall. A firewall that another entry names as its `ha_backup` is checked as a backup: every VIP is expected BACKUP, a MASTER VIP is an error, and there is no role warning or split check. See [ADR-0024](../decisions/0024-opnsense-firewalls-are-provider-instances-several-per-environment.md).

## Firmware Updates

`system.firmware` can update the box to the latest minor release before it installs plugins. Set `update: true`; `update_timeout` (seconds, default `1800`) covers the update job and the reboot wait. Without `update`, nothing changes and no update endpoint is called.

```yaml
opnsense:
  system:
    firmware:
      update: true
      plugins:
        - os-acme-client
```

`infra plan` runs a firmware check and lists a pending update as a change. **An update can reboot the firewall**; the plan warns when OPNsense expects one. `infra apply` starts the update, waits for the job and the reboot, confirms the new version, then installs plugins and writes settings. Major upgrades are not supported. Settings such as `mirror`, `type` and `reboot` written in the same apply take effect from the next update. Details: [System firmware update (#1452)](../development/opnsense-resource-coverage.md#system-firmware-update-1452).

**Fresh box in one apply (#1458).** A box built from a base-release image can lack the endpoints a type needs, such as `firewall.source_nat` before OPNsense 26.1. Without `update: true`, such a type fails the plan with its usual error and nothing is applied. With `update: true` in the same run, the type is deferred instead: the plan lists it as "deferred until the firmware update". `infra apply` then runs the gateway step first (`interfaces.vlans`, `interfaces.assignments`, `routing.gateways`, whichever are in the run), so the box has a route to fetch the update. Next it applies `system.firmware`, then every other type in table order. It then re-checks the deferred types against the updated box and applies them. A type that the updated box still cannot serve fails with the normal error. `system.firmware` itself is never deferred. Without `update: true` the apply order and behavior are unchanged. The delete pass keeps its order (reverse table order).

## Endpoint and Version Check

During `infra plan` (and so `infra apply`) and `infra doctor`, the box's OPNsense version is read and each type's endpoints are checked against it (`check_endpoint_support`). A type whose endpoints that version lacks is reported as an error, and an unreadable setting or unknown version is reported as a warning. See [Endpoint registry and version check](../development/opnsense-resource-coverage.md#endpoint-registry-and-version-check-1239).

## Validation and Checks

```bash
foundry infra doctor --env <env> -P opnsense
```

The check tests connectivity to the API (`validate_connectivity`), that referenced OPNsense resources exist, and the endpoint support described above (`validate_references`).

`infra doctor` also warns when a `kea.dhcp4.subnets` entry sets `auto_collect: true` together with `routers`, `dns_servers` or `ntp_servers`. Saving the Kea DHCPv4 settings re-runs auto-collect and overwrites those values; set `auto_collect: false` to keep them. See [Kea DHCPv4 high availability](../development/opnsense-resource-coverage.md#kea-dhcpv4-high-availability-1392).

`infra plan`, `infra apply` and `infra doctor` warn when a CARP `vhid` is reused on more than one interface, and fail when a CARP virtual IP lies outside the static subnet of its interface in config (or outside the subnet of an `ipalias` virtual IP on that interface). The subnet check is skipped when the interface address is not static in config, and for `ipalias` and `proxyarp` virtual IPs.

`infra doctor` also reports CARP pair health. It reads the CARP VIP state and, when `synchronize_to_ip` is set, asks the peer for its version through `core/hasync_status/version`. A node with `synchronize_to_ip` set is the sync source and is expected to be MASTER on every VIP. The report is an error when a VIP is not MASTER on the sync source, when a VIP is in INIT or DISABLED, when MASTER and BACKUP VIPs are mixed on a node with no sync target, when CARP is disabled (`allow` is 0), or when the peer does not answer. It is a warning when maintenance mode is on, the demotion counter is above 0, there are CARP VIPs but no `synchronize_to_ip` (the role is unknown), or the peer answers without a version. A single node, with no CARP VIPs and no sync target, produces no output. The per-VIP lines appear with `--verbose`. An unreachable peer takes about 60 seconds to report, and never longer than `ha_sync_timeout`. A both-MASTER split cannot be seen from the primary alone; an unreachable peer is reported as "cannot be ruled out". See [CARP pair health](../development/opnsense-resource-coverage.md#carp-pair-health-1393).

That warning also appears on `infra plan` and `infra apply`, which run the OPNsense checks that need no API access. The checks that compare against the live box (aliases, interfaces, gateways, Unbound overrides) remain doctor-only. See [Validation during plan and apply](../usage/validation.md#validation-during-plan-and-apply).

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
- **A firmware update fails or times out.** The error carries the tail of the firmware log. Raise `update_timeout` if the box was still rebooting, and check the box before re-applying; a second apply continues from the current version.
- **Connection or authentication errors.** See [IF-API-002](../reference/errors.md#if-api-002-connection-failed) and [IF-API-003](../reference/errors.md#if-api-003-authentication-failed), and run `foundry infra doctor --env <env> -P opnsense`.
- **Unsupported resource type.** See [Unsupported types](#unsupported-types).
- **Anything else.** See [Troubleshooting Common Errors](../guides/troubleshooting.md).
