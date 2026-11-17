---
title: "ADR-0024: OPNsense firewalls are provider instances, several per environment"
description: Each extra OPNsense firewall is a provider instance opnsense@name, and the primary keeps the plain opnsense id
date: 2026-11-17
audience:
  - contributors
tags:
  - adr
---

# ADR-0024: OPNsense firewalls are provider instances, several per environment

## Status
Accepted

## Context
An environment could address one OPNsense firewall: `provider_settings.opnsense` held one `api_url`, `api_key` and `api_secret`. An HA pair, or two independent firewalls, could not be managed from one environment. Managing a backup node meant a second environment, which duplicates configuration and splits state. Issue #1450 asks for several firewalls per environment, each with its own managed set, deletes, HA sync and doctor report, without breaking existing flat configurations or state rows.

## Decision
Each extra firewall is its own **provider instance**. The primary firewall keeps the provider id `opnsense`; every other one is `opnsense@<name>`.

- **Config shape:** `provider_settings.opnsense.firewalls` maps a name to per-firewall settings (`api_url`, `api_key`, `api_secret`, `ssh_*`, `verify_ssl`, `proxy`, `ha_sync_after_apply`, `ha_sync_timeout`, `ha_backup`). `primary` names the primary and is required with more than one entry. Top-level `verify_ssl`, `proxy`, `ssh_user`, `ssh_port`, `ssh_key` and `ha_sync_*` are shared defaults that an entry overrides. The flat `api_url`/`api_key`/`api_secret` shape is unchanged and means one unnamed firewall; combining it with `firewalls:` is an error. Names match `^[a-z0-9][a-z0-9-]{0,31}$`, which keeps `opnsense@<name>` inside the 50-character provider column.
- **Choosing a firewall for a resource**, most specific first: the entry's own `firewall:` key, then a file-level `firewall:` beside `opnsense:`, then the package manifest's `firewall:`, then the primary. Dict singletons such as `hasync.settings` take the file or package default.
- **Primary normalization:** the loader stamps `opnsense@<name>`, and `ConfigManager` rewrites the primary's stamp to plain `opnsense`. Converting a flat configuration to `firewalls:` therefore keeps its state rows.
- **State identity:** no schema change and no migration. Rows of an instance carry `provider="opnsense@<name>"`; legacy rows are identical to the primary's. `state list --provider opnsense` matches exactly, so a backup's rows list under `opnsense@<name>`.
- **Environment overrides:** `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE` and the `OPNSENSE_*` variables apply only to the primary. An instance ignores them and a WARNING is logged once per process, so one override cannot retarget every firewall to the same endpoint.
- **Execution:** the executor already runs one batch per provider id, so each firewall plans, applies and destroys in its own batch, with its own managed set, deletes and `post_apply_hook` (HA sync). `ExecutionPlanner` orders an instance right after its base provider (reverse on destroy).
- **CLI:** the core provider filter still matches ids exactly. A CLI helper expands `-P opnsense` to the primary plus every declared instance that has resources, and a repeatable `--firewall <name>` selects exact firewalls. `--firewall` is mutually exclusive with `-p` and `-r`.
- **Output:** runner lines read `opnsense_direct[<name>]: ...` and doctor and offline results carry a `[<name>] ` prefix, only when `firewalls:` is declared. Flat configurations print as before.
- **Pair check:** a firewall entry may set `ha_backup: <name>`. `infra doctor` then reads `getVipStatus` on both nodes, each through its own client, and a `CarpPairValidator` compares every VIP by `(vhid, subnet)`. MASTER on this node with BACKUP on the backup passes. A VIP missing on the backup, MASTER on both, or any other state is an ERROR. An unreadable backup is a WARNING. The per-node `CarpHealthValidator` still runs for each firewall.

## Rationale
Most per-firewall behaviour already hangs off the provider id: the duplicate-name check (`provider:name`), the state `provider` column and `get_managed`, dependency graph nodes, executor batches, post-apply hooks and validation reports. A provider instance reuses all of it. Because validators see only their own firewall's resources, the same VIP or VHID on two firewalls is not a reuse error, and the same resource name on both firewalls does not collide.

Alternatives rejected:

- **A `target` field on `ResourceConfig`.** Core uses `resource.name` as identity in about ten places (executor resource ids, events, released resources, managed `(type, name)`, `-r`). A target field needs a state column, a migration and a much larger core change.
- **Qualifying resource names (`fw-b/lan`).** 31 of 51 components match live objects by `resource.name`; `interfaces.assignments` uses it as the live identifier, so `lan` must stay `lan` on both nodes.
- **A second environment per firewall.** Duplicates configuration and splits state, which is the problem being solved.

## Related Issues

- Issue #1450: support more than one opnsense firewall per environment
- Issue #1442: trigger OPNsense HA config sync after destroy
- Issue #1393: CARP health in infra doctor

## Related Documentation

- [OPNsense provider: several firewalls per environment](../providers/opnsense.md#several-firewalls-per-environment)
- [ADR-0014: OPNsense direct API](0014-opnsense-direct-api-apply-mechanism.md)
