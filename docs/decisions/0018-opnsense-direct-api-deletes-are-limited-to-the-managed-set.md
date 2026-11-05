---
title: "ADR-0018: OPNsense direct-API deletes are limited to the managed set"
description: "opnsense_direct deletes only the objects the state database records as managed, and a type with no YAML entries is still dispatched to delete them"
date: 2026-11-05
audience:
  - contributors
tags:
  - adr
---

# ADR-0018: OPNsense direct-API deletes are limited to the managed set

## Status

Accepted

## Decision

`opnsense_direct` deletes only the objects InfraFoundry manages. The managed set comes from the state database, and a live object that InfraFoundry never applied is kept whether or not its type has YAML entries. This applies to all sixteen list types. It partly supersedes the "fully-managed by default" rule in [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) section 5 for unmanaged objects.

**The managed set.** The `resources` table is append-only: every plan inserts a `PLANNED` row, and a destroy inserts a new row marked `DELETED` while the older `ACTIVE` rows stay. For each `(resource_type, name)` the newest row (by `id`) whose state is `ACTIVE` or `DELETED` decides. The entry is managed when that row is `ACTIVE`. `ResourceRepository.get_managed(environment, provider)` applies the rule and `StateManager.get_managed_resources` delegates to it. There is no schema change and no row migration.

**Passing it to the runner.** `PlanOrchestrator.plan` (non-dry-run) and `DeploymentExecutor.apply_single_provider` rebuild the rows as `ResourceConfig` objects with `core/managed_set.py::build_managed_resources` and pass them as `managed_resources=` to `runner.plan` and `runner.apply`. A manager opts in with a `DELETE_SCOPE` class variable:

- `"managed_set"`: the manager receives `managed_resources` and its diff engine deletes a live object only when the object's key is in the set derived from those rows. Other live objects missing from YAML go to a new `Diff.unmanaged` list, which `is_empty` ignores. The plan summary shows them as `N unmanaged (kept)`.
- `"marker"`: `firewall.rules`, `firewall.nat` and `cron.jobs` already delete only objects carrying InfraFoundry's marker, so they need no managed set.

A type with no YAML entries is dispatched only when the run has a managed set, is not add-only (filtered runs are add-only), the manager has a `DELETE_SCOPE`, and the type has managed rows. That is what makes removing the last YAML entry of a type delete its object. Without a managed set the runner behaves as before.

**Recording releases.** After a full-mode apply of a type succeeds, the runner returns the managed names of that type that are no longer in YAML as `released_resources`. Once the runner reports success, the executor inserts one `DELETED` row per released resource (the same insert-a-row pattern destroy uses), so the next run stops treating it as managed. A name is released when its key resolved, whether or not the object is still live (an object already gone is released). A managed row the manager could not resolve to a key stays managed: it has no `DELETED` row recorded, so the next run retries it and warns again. Each manager reports those names as `unresolved_managed` on its apply result, and the runner leaves them out of `released_resources`. That covers rows that fail to parse (through the shared `managed_keys` helper), kea subnet rows with no `subnet`, reservation rows with no MAC or DUID or with an unresolvable subnet and no orphan match, and host-alias rows with neither a resolved parent nor an orphan match. If an apply fails partway, the release is lost for that run and the next full apply releases it.

**How each family derives its key.** Rows are parsed one at a time. A row that fails to parse is skipped and logged by type and name only, never its config, and a row whose key cannot be derived is never deleted. Deriving keys never resolves secrets.

| Types | Key | Derivation |
| :--- | :--- | :--- |
| `interfaces.vlans`, `firewall.aliases`, `routing.gateways`, `routing.static`, `interfaces.virtual_ips`, `unbound.host_overrides`, `unbound.forwards` | The type's natural key | The type's `*_configs_from_resources` parser, then `.diff_key` (`components/_managed.py::managed_keys`) |
| `kea.dhcp4.subnets`, `kea.dhcp6.subnets` | Subnet CIDR | `config["subnet"]` of the row |
| `unbound.host_aliases` | `(parent_uuid, hostname)` | The row's `host_name` resolved against the live host overrides, without raising |
| `kea.dhcp4.reservations`, `kea.dhcp6.reservations` | `(hw_address or duid, subnet_uuid)` | The row's subnet CIDR (through the YAML and managed subnets), then the live subnet UUID |
| `interfaces.assignments` | Logical identifier | Config only, with the `lan` and `wan` guard below |
| `firewall.rules`, `firewall.nat`, `cron.jobs` | Marker name | Existing marker scoping |

**Parent and child types.** The dispatch table applies `unbound.host_overrides` before `unbound.host_aliases`, and kea subnets before kea reservations. When a parent and its children leave YAML together, the parent is deleted first and the child's parent no longer resolves. For a managed row whose parent does not resolve, the engine matches live orphans: aliases whose parent UUID is not any live override's, with the same hostname and domain, matched only when exactly one live orphan fits (an ambiguous match could delete an alias InfraFoundry never applied); reservations whose subnet UUID is not a live subnet's, with the same MAC or DUID. A managed row with neither a resolved parent nor an orphan match is skipped with a warning (fail closed), kept as managed and retried. YAML rows keep their strict resolution and still raise.

**Unverified on a live box.** Whether OPNsense cascades the child when its parent is deleted, refuses the parent delete, or leaves an orphan has not been checked, because no box was contacted. If it cascades, the plan shows the child delete (the parent is still live when the plan runs) but the apply counts none for it. The full reconcile this replaces had the same ordering, so this change does not make it worse. A live check after merge is requested in the PR.

**`lan` and `wan` guard.** `find_lockout_conflicts` checks adds and updates only, so with no YAML entries for `interfaces.assignments` a restricted delete could remove the assignment the API is reached through. In restricted mode a managed `lan` or `wan` is never deleted: it goes to `unmanaged` with a warning. Assignments that are neither but carry the management address are still deletable. Keep the management interface in YAML with `lock: true`.

**Upgrade path.** Existing rows are read correctly by the latest-row rule. On the first plan after upgrade, types that were skipped because they had no YAML entries now show a delete for each object InfraFoundry once applied. That is the intended fix. Types with entries produce nothing for old names whose objects are already gone, and release them on the first full apply. Hand-added objects show as `unmanaged (kept)`.

## Rationale

- **The state database is the only record of what InfraFoundry applied.** The runner has no `StateManager` of its own, so the orchestrator and executor read the rows and hand them over.
- **The issue's "non-`DELETED` rows" rule is wrong for this table.** Plans add `PLANNED` rows and destroys leave older `ACTIVE` rows in place, so only the newest `ACTIVE` or `DELETED` row tells the current state.
- **Breaking change.** Objects added by hand next to managed ones used to be deleted by the full reconcile and are now kept. This reverses ADR-0014 section 5 for unmanaged objects. It is released with a `BREAKING CHANGE:` footer.
- **No opt-out flag and no phases.** All sixteen list types change together, so there is one rule for operators.

### Known limit

Removing the environment's last `provider: opnsense` resource still leaves its objects on the box, because the provider is never dispatched when it has no resources. This is out of scope here and tracked in #1260.

Singleton types (`system.*`, `unbound.advanced`, `radvd`) are unaffected. `radvd` reconciles fully inside its own component.

## Documentation

Operator-facing behavior is described in [OPNsense resource coverage: how deletes work](../development/opnsense-resource-coverage.md#how-deletes-work-the-managed-set-1256).

## Related Issues

- [#1256](https://github.com/endavis/infrafoundry/issues/1256): feat: let `opnsense_direct` delete only the objects InfraFoundry manages.
- [#1252](https://github.com/endavis/infrafoundry/issues/1252): documented and pinned the last-list-entry limitation this change removes.
