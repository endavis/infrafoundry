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

**Amended:** 2026-11-05 (#1264) - kea deletes run in a reverse-order phase, and a subnet delete is refused while reservations InfraFoundry does not manage still use it

**Amended:** 2026-11-05 (#1269) - every type with a dependency in the dispatch table splits its deletes, and gateways and static routes are dispatched before firewall rules

**Amended:** 2026-11-08 (#807) - `trust.cas` and `trust.certs` join the managed-set types; certificates split their deletes ahead of CAs, and objects the box reports in use (or CAs that look AcmeClient-issued) are kept

**Amended:** 2026-11-08 (#808) - `openvpn.instances` (OpenVPN client instances) joins the managed-set types and splits its deletes ahead of `trust.cas`; only client instances are ever matched or deleted, a live server instance is never touched

**Amended:** 2026-11-09 (#790) - `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions` and `acmeclient.certs` join the managed-set types, keyed by the wire name (the CN for certs); certs split their deletes ahead of the other three

## Decision

`opnsense_direct` deletes only the objects InfraFoundry manages. The managed set comes from the state database, and a live object that InfraFoundry never applied is kept whether or not its type has YAML entries. This applies to all nineteen list types. It partly supersedes the "fully-managed by default" rule in [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) section 5 for unmanaged objects.

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
| `trust.cas`, `trust.certs` | `descr` (the YAML `description`, default the name) | The type's `*_configs_from_resources` parser, then `.diff_key`; no secret resolution is needed |
| `openvpn.instances` | `description` (the YAML `description`, default the name) | The type's `openvpn_instance_configs_from_resources` parser, then `.diff_key`; secrets stay `secret://` URIs, so no resolution is needed |
| `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions`, `acmeclient.certs` | The wire `name` (`display_name`, else the YAML name; `common_name` for certs) | The type's `configs_from_resources` parser, then `.diff_key`; secrets stay `secret://` URIs, so no resolution is needed |
| `kea.dhcp4.subnets`, `kea.dhcp6.subnets` | Subnet CIDR | `config["subnet"]` of the row |
| `unbound.host_aliases` | `(parent_uuid, hostname)` | The row's `host_name` resolved against the live host overrides, without raising |
| `kea.dhcp4.reservations`, `kea.dhcp6.reservations` | `(hw_address or duid, subnet_uuid)` | The row's subnet CIDR (through the YAML and managed subnets), then the live subnet UUID |
| `interfaces.assignments` | Logical identifier | Config only, with the `lan` and `wan` guard below |
| `firewall.rules`, `firewall.nat`, `cron.jobs` | Marker name | Existing marker scoping |

**Parent and child types.** The dispatch table applies `unbound.host_overrides` before `unbound.host_aliases`, and kea subnets before kea reservations. For kea, deletes run the other way (#1264). The four kea managers declare `SPLIT_DELETE_PHASE`, and the runner first calls each of them with `deletes_only=True` in reverse table order (reservations, then subnets). The forward pass then calls them with `add_only=True`. A managed reservation is therefore deleted while its subnet is still live, so its key resolves through the managed subnet row and the live CIDR, and the release is recorded from the first phase. `destroy` uses the same order. The orphan matching stays as a safety net: for a managed row whose parent does not resolve, the engine matches live orphans (aliases whose parent UUID is not any live override's, with the same hostname and domain, matched only when exactly one live orphan fits; reservations whose subnet UUID is not a live subnet's, with the same MAC or DUID). A managed row with neither a resolved parent nor an orphan match is skipped with a warning (fail closed), kept as managed and retried. YAML rows keep their strict resolution and still raise.

**General rule (#1269).** Every type that depends on another table type declares `SPLIT_DELETE_PHASE`: besides the kea managers, `firewall.rules`, `firewall.nat`, `routing.gateways`, `routing.static`, `interfaces.virtual_ips`, (#1271) `interfaces.assignments` and (#1272) `radvd`, (#807) `trust.certs` and (#808) `openvpn.instances` and (#790) `acmeclient.certs`. A child then always deletes before its parent, whether or not the parent also splits. The dispatch table is also kept in dependency order, so `routing.gateways` and `routing.static` are applied before `firewall.rules`. Assignments split because OPNsense refuses to delete an assigned VLAN; their apply lists live state first and runs the SSH preflight and controller install only when the diff has writes, so the two passes do not repeat them. `radvd` splits too: its `add_only` now suppresses deletes only, like every other manager, so the forward pass keeps its updates, and a radvd record is deleted before its assignment (#1272). One dependent type is exempt: `unbound.host_aliases` (OPNsense cascades the delete).

**Verified on a live box (#1264).** OPNsense kea `delSubnet` neither cascades to the subnet's reservations nor refuses: they stay, pointing at the deleted UUID. Unbound `delHostOverride` does cascade to its aliases, so unbound needs no delete phase.

**Refusing a subnet delete.** A subnet is not deleted while a reservation InfraFoundry does not manage still uses it, such as a hand-made one. The plan keeps the subnet, shows `N blocked (kept)` and a warning naming the CIDR and each reservation's MAC or DUID and IP. The apply checks the box after the reservation deletes, skips the subnet with the same warning, and keeps its row managed so the next run retries and warns again. It does not fail the apply, because that would block unrelated changes over an object outside InfraFoundry's control. `destroy` skips such a subnet with a warning. The operator removes or moves the reservation on the box and re-runs apply.

**`lan` and `wan` guard.** `find_lockout_conflicts` checks adds and updates only, so with no YAML entries for `interfaces.assignments` a restricted delete could remove the assignment the API is reached through. In restricted mode a managed `lan` or `wan` is never deleted: it goes to `unmanaged` with a warning. Assignments that are neither but carry the management address are still deletable. Keep the management interface in YAML with `lock: true`.

**Upgrade path.** Existing rows are read correctly by the latest-row rule. On the first plan after upgrade, types that were skipped because they had no YAML entries now show a delete for each object InfraFoundry once applied. That is the intended fix. Types with entries produce nothing for old names whose objects are already gone, and release them on the first full apply. Hand-added objects show as `unmanaged (kept)`.

## Rationale

- **The state database is the only record of what InfraFoundry applied.** The runner has no `StateManager` of its own, so the orchestrator and executor read the rows and hand them over.
- **The issue's "non-`DELETED` rows" rule is wrong for this table.** Plans add `PLANNED` rows and destroys leave older `ACTIVE` rows in place, so only the newest `ACTIVE` or `DELETED` row tells the current state.
- **Breaking change.** Objects added by hand next to managed ones used to be deleted by the full reconcile and are now kept. This reverses ADR-0014 section 5 for unmanaged objects. It is released with a `BREAKING CHANGE:` footer.
- **No opt-out flag and no rollout phases.** All sixteen list types change together, so there is one rule for operators.

### Known limit

Removing the environment's last `provider: opnsense` resource used to leave its objects on the box, because the provider was never dispatched when it had no resources. #1260 closes this. The orchestrator asks managed-set runners (the `DispatchesManagedSet` protocol) whether a provider absent from YAML needs dispatching, and adds it with an empty resource list, for full non-dry-run runs only.

Singleton types (`system.*`, `unbound.advanced`, `interfaces.settings`, `syslog.settings`, `radvd`) are unaffected. `radvd` reconciles fully inside its own component.

## Documentation

Operator-facing behavior is described in [OPNsense resource coverage: how deletes work](../development/opnsense-resource-coverage.md#how-deletes-work-the-managed-set-1256).

## Related Issues

- [#1256](https://github.com/endavis/infrafoundry/issues/1256): feat: let `opnsense_direct` delete only the objects InfraFoundry manages.
- [#1260](https://github.com/endavis/infrafoundry/issues/1260): dispatches `opnsense_direct` when an environment's last opnsense resource is removed.
- [#1264](https://github.com/endavis/infrafoundry/issues/1264): kea deletes reservations before subnets and refuses a subnet delete that would orphan unmanaged reservations.
- [#1269](https://github.com/endavis/infrafoundry/issues/1269): dispatches gateways and static routes before firewall rules and extends the delete phase to every dependent type.
- [#1271](https://github.com/endavis/infrafoundry/issues/1271): splits interface assignment deletes so an assignment is deleted before the VLAN it uses.
- [#1272](https://github.com/endavis/infrafoundry/issues/1272): splits radvd deletes so a radvd record is deleted before its interface assignment, and makes radvd `add_only` suppress deletes only.
- [#1252](https://github.com/endavis/infrafoundry/issues/1252): documented and pinned the last-list-entry limitation this change removes.
