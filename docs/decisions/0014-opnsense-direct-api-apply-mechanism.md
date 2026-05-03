# ADR-0014: OPNsense Direct-API Apply Mechanism

**Date:** 2026-04-30
**Amended:** 2026-05-03 (#717, PR #718) — added second internal write path for resources with no native REST CRUD; records `interface_assignments` per-component decision
**Status:** Accepted

## Status

Accepted

## Decision

OPNsense resources will be managed by a **direct-API apply mechanism** built on the [`opnsense_openapi`](https://github.com/endavis/opnsense-openapi) Python package, replacing the current Terraform + browningluke + Ansible pipeline as the per-component implementation issues from ADR-0013 land.

The decision answers the nine open questions deferred from [ADR-0013](0013-opnsense-full-iac-migration.md). It is grounded in the live VLAN spike documented in [`opnsense-spike-vlan-findings.md`](../development/opnsense-spike-vlan-findings.md) (PR [#706](https://github.com/endavis/infrafoundry/pull/706), merged commit `584ac10`), which exercised add/update/delete + idempotency + `lock` + `--add-only` + dry-run end-to-end against `opnsense-a` running `26.1.6_2`.

### 1. Apply mechanism for new components

**Direct-API via `opnsense_openapi`.** The 736-line spike covered every operation the production path needs in a single readable Python module with one runtime dependency and zero external binaries. The Terraform + `browningluke/opnsense` + Ansible-reload pipeline is retained only until each existing component is migrated; net-new components ship under direct-API immediately.

**Component-installed REST controllers** are a recognized second internal write path inside `OPNsenseDirectRunner` for resource types where OPNsense's stock API surface has no CRUD endpoint. The pattern: a small PHP controller is installed once at `/usr/local/opnsense/mvc/app/controllers/OPNsense/<Module>/Api/`; subsequent operations use REST exclusively. Install requires SSH (one-time per box; idempotent verify-and-reinstall on each `infra apply` is acceptable for production); ongoing apply does not. The first such controller is `AssignSettingsController.php` for `interface_assignments`, validated in PR #716. Each new controller-installed REST mechanism is a discrete decision recorded in this ADR's "Per-component decisions" section. Ownership: when InfraFoundry forks a community controller, the fork lives in-tree under `tools/spikes/.../` (or graduates to `src/infrafoundry/providers/<provider>/extensions/...` once production-bound), and InfraFoundry maintains it.

### 2. Schema source

**Pydantic models from OPNsense's OpenAPI spec, accessed via `opnsense_openapi.list_endpoints()` and the matched spec file.** Where the spec disagrees with a live box (see [`#32`](https://github.com/endavis/opnsense-openapi/issues/32) — controller-name bug for multi-word controllers), components fall back to hand-typed dicts at the impacted call sites. `auto_detect_version=True` correctly resolved `26.1.6_2` against the bundled `26.1.6` spec during the spike, so version pinning is not required.

### 3. Client surface

**Default to the bare `client.post(...)` / `client.get(...)` fallback.** The typed `.api.<module>.<call>` surface is revisited only after upstream [`#32`](https://github.com/endavis/opnsense-openapi/issues/32) (blocker), [`#33`](https://github.com/endavis/opnsense-openapi/issues/33), and [`#34`](https://github.com/endavis/opnsense-openapi/issues/34) land. The typed surface is a `__getattr__` proxy at runtime — mypy and pyright cannot validate call sites against it — so the value-add over the fallback is Pydantic *payload* validation only, not call-site type-checking. The fallback path covered every spike operation cleanly (search, add, delete, reconfigure) without introducing the `openapi-python-client` external CLI dependency.

### 4. Runner integration

**Introduce `OPNsenseDirectRunner(BaseRunner)`.** The new runner implements the relevant [ADR-0010](0010-protocol-based-runner-interfaces.md) protocols — `Plannable`, `Applyable`, `Destroyable`, `StateAware` — by delegating to direct-API provider methods. The Provider → Component Manager → Service Layer arrangement stays unchanged and matches today's Kea DHCP pattern (`src/infrafoundry/providers/opnsense/components/kea_dhcp.py` + `services/kea_dhcp.py`). Net effect: `foundry infra plan` and `foundry infra apply` see direct-API resources alongside Terraform-managed ones with no second command needed and no bypass of the runner system.

The runner's `tool_name` is `opnsense_direct` (underscore, not hyphen): `orchestrator_workflows.py` dispatches via `getattr(provider, f"generate_{tool_name}", None)`, so the tool name must be a Python identifier.

### 5. Default semantics

**Fully-managed by default; `--add-only` is an opt-in CLI flag.** Env-root packages are the source of truth, and additive-by-default would let drift accumulate silently. The spike's first live `plan` against staging proposed deleting the WAN VLAN (`ixl0` tag 4000) precisely because it was absent from the test YAML — that is the contract working as designed. Cutover migrations, where a single env transitions from manual configuration to IaC piecemeal, opt into `--add-only` for the migration window.

### 6. Lock contract

**Boolean `lock: true` under `config:`** on the resource entry. The spike's example placed `lock` at the resource top level; that doesn't survive InfraFoundry's `ResourceConfig` Pydantic schema (`src/infrafoundry/core/provider.py:14-24`), which is a `BaseModel` without `extra="allow"` and silently drops top-level extras. To avoid the silent-drop footgun, the production contract puts `lock` under `config:`:

```yaml
- provider: opnsense
  type: vlans
  name: wan-trunk
  config:
    device: ixl0
    tag: 4000
    description: WAN trunk
    priority: 0
    lock: true
```

Granular locks (`lock: { delete: true, update: false }`) are deferred to a follow-up ADR if pain emerges. The boolean form was sufficient for every spike scenario (preserving the WAN trunk through repeated apply cycles) and keeps the YAML schema a single field rather than a polymorphic value.

### 7. Plan-time validation

**Yes — `plan` validates `device:` and other interface references against the live box.** The spike caught a bad NIC name (`igb1` against a box with only `ixl0`/`ixl1`) only at apply time; that class of error must surface during `plan`. The validation pattern already exists in `src/infrafoundry/providers/opnsense/validator.py` (`validate_references()`) and adds one extra API call per plan, well within acceptable cost.

### 8. `config migrate` integration

**Per-component method on the OPNsense provider, hardcoded to the CLI's choice list.** This matches today's Kea DHCP pattern. A pluggable extractor registry is acknowledged as a follow-up but is out of scope for ADR-0014; nothing in the migrate flow blocks on it.

### 9. Migration of existing Terraform-based paths

**Phased migration to direct-API as part of ADR-0013's implementation phase.** Net-new components from ADR-0013's list (`interface_assignments`, NAT rules, gateways, static routes, virtual IPs, Unbound extensions) ship under direct-API immediately. Existing Terraform-based paths migrate in priority order:

1. **VLANs** — the spike code is the seed; first to land.
2. `aliases`, `firewall_rules`, `unbound_host_override`.
3. `kea_subnet` / `kea_reservation` / `dhcp_static_maps` (these already use the OPNsense REST API directly via `opnsense_openapi`; the work is normalizing them onto `OPNsenseDirectRunner`).

The `templates/opnsense/playbook.yml.j2` Ansible service-reload playbook retires once the last Terraform-based component is gone.

> **Note (interface_assignments, #711, amended 2026-05-03):** OPNsense `26.1.6_2` exposes no REST CRUD for `<interfaces>`. The component shipped read-only in PR #712 (`list` / `migrate` / validation work; `apply` / `destroy` are loud no-ops). The write path is decided in this ADR's "Per-component decisions" section: server-side-validated REST via a forked, in-tree PHP controller (PR #716 spike). Production conversion (`OPNsenseDirectRunner.apply()` from no-op to live for this resource) is gated on the production conversion issue, which carries out gates (2) and (3) recorded above.

## Per-component decisions

Each new write mechanism that diverges from §1's default (REST via `opnsense_openapi`) is recorded here.

### `interface_assignments` (PR #716, 2026-05-02 spike; production conversion gated on this amendment)

**Mechanism:** Server-side-validated REST via the forked `AssignSettingsController.php` controller installed at `/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/`.

- **Read side:** `interfaces/overview/interfacesInfo` (already in production from PR #712, no controller required).
- **Write side:** `assign_settings/{addItem, setItem, getItem, searchItem, delItem}` against the installed controller.
- **Fork location:** in-tree at `tools/spikes/interface_assignment_gist_rest/AssignSettingsController.php` for the spike phase; production conversion graduates it to `src/infrafoundry/providers/opnsense/extensions/...`.
- **Patches/extensions over the upstream gist:** `sessionClose()` removed (modern-OPNsense compatibility), IPv6 fields, `setItem` / `getItem` / `searchItem`, optional explicit `name: optN`, validation helpers. ~225 LoC net-new on top of ~345 LoC inherited from szymczag's BSD-2-Clause base.

**Rollback strategy:** No transactional rollback (option (c) from the findings doc).

The spike empirically established that `/api/core/backup/{backups,download}` returns HTTP 404 on `26.1.6_2`, so the original auto-rollback design is unavailable on this OPNsense version. Three options surfaced; this ADR adopts (c) for the following reasons:

- **Per-call server-side validation is the primary safety net.** Every `addItem`/`setItem`/`delItem` POST flows through OPNsense's standard `Config::getInstance()->save()`. Bad input (invalid IPv4, unknown `ipv4Type`, missing `device`) is rejected with HTTP 400 *before* any state change. The spike verified all three cases live.
- **OPNsense's auto-snapshot is the residual safety net.** `Config::save()` captures a pre-write snapshot in `/conf/backup/` (visible in System → Configuration → Backups in the GUI). Operators can manually revert from there for the "correct-but-undesired apply" case that validation can't catch.
- **Option (a) is wishful** — no alternative snapshot endpoint surfaced during the spike's REST probe.
- **Option (b) re-introduces SSH** into the safety path for rollback. The gist-based mechanism's premise was to remove SSH from the steady-state apply path; reusing it for rollback erodes that win. Rejected.

**Preconditions for production conversion** (carried out by the production conversion issue, not this amendment):

- **Gate (2):** Empirically confirm that an `addItem`/`setItem`/`delItem` REST call produces a new entry in System → Configuration → Backups (auto-snapshot) AND System → Log Files → System General (audit log). The PHP controller calls OPNsense's standard `Config::save()` write path, so both should fire — but production lift can't proceed without empirical confirmation.
- **Gate (3):** Security review of the ~225 LoC of net-new PHP in the forked controller. Community-authored code deployed to root on production firewall infrastructure requires a deliberate review pass. BSD-2-Clause is compatible.

**Cross-reference:** [ADR-0013 §"Per-component decisions recorded so far"](0013-opnsense-full-iac-migration.md#per-component-decisions-recorded-so-far) updated to reflect this resolution. See also [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../development/opnsense-spike-interface-assignment-gist-findings.md) for the load-bearing evidence.

## Rationale

The VLAN spike supplied the load-bearing evidence:

- **Round-trip property holds.** `plan` after `apply --confirm` returned 0/0/0 for both add and delete cycles. See [Round-trip property](../development/opnsense-spike-vlan-findings.md#round-trip-property).
- **Fallback client is sufficient.** `openapi-python-client` was not installed; the typed `.api` surface was never exercised; the fallback `client.post(...)` path covered every operation cleanly. See [Run log](../development/opnsense-spike-vlan-findings.md#run-log) and [Typed-surface coverage](../development/opnsense-spike-vlan-findings.md#typed-surface-coverage).
- **Lock + add-only are necessary, not optional.** Pure fully-managed mode is dangerous mid-cutover (the staging WAN VLAN would have been deleted on the first run had the test YAML not been amended). Both safety affordances were exercised live. See [Friction points](../development/opnsense-spike-vlan-findings.md#friction-points).
- **Cost trade-off is favorable.** ~600 lines of direct-API plumbing replaces three external tools (terraform binary, browningluke provider, Ansible) and the spec-vs-live drift overhead they introduce. See [Lines of code per concern](../development/opnsense-spike-vlan-findings.md#lines-of-code-per-concern).

The runner integration via ADR-0010 protocols keeps the CLI surface consistent: operators run `foundry infra plan` and `apply` regardless of whether a given component is Terraform-backed or direct-API-backed during the migration window.

### Prerequisites for the implementation phase

- Upstream [`endavis/opnsense-openapi#32`](https://github.com/endavis/opnsense-openapi/issues/32) fixed before any consumer relies on the typed `.api` surface. The fallback path does not block on `#32` for individual call sites that hardcode the corrected controller name (as the spike's `vlan_settings` constant does).
- [`#33`](https://github.com/endavis/opnsense-openapi/issues/33) and [`#34`](https://github.com/endavis/opnsense-openapi/issues/34) are nice-to-have, not blocking.

### Known follow-ups (not in scope here)

- Pluggable extractor registry for `config migrate` (see decision #8).
- Granular lock semantics if boolean `lock: true` proves insufficient (see decision #6).
- Lossy round-trip validation (descriptions with quotes/unicode/long strings) before any production lift; see the [Round-trip property](../development/opnsense-spike-vlan-findings.md#round-trip-property) caveat.
- Retirement of `templates/opnsense/playbook.yml.j2` after the last Terraform-based component migrates (see decision #9).

## Related Issues

- Issue [#709](https://github.com/endavis/infrafoundry/issues/709): feat: add `OPNsenseDirectRunner` and migrate VLAN component to direct-API (first implementation).
- Issue [#711](https://github.com/endavis/infrafoundry/issues/711): feat: add OPNsense `interface_assignments` component (read-only / migrate; dispatch-table refactor).
- Issue [#707](https://github.com/endavis/infrafoundry/issues/707): chore: write ADR-0014 codifying OPNsense direct-API apply mechanism (this ADR).
- Issue [#705](https://github.com/endavis/infrafoundry/issues/705): feat: spike direct-API VLAN component to inform ADR-0014 (closed; PR [#706](https://github.com/endavis/infrafoundry/pull/706) merged).
- Issue [#701](https://github.com/endavis/infrafoundry/issues/701): the ADR-0013 work that deferred this decision (PR [#704](https://github.com/endavis/infrafoundry/pull/704)).
- Upstream [`endavis/opnsense-openapi#32`](https://github.com/endavis/opnsense-openapi/issues/32): bug — spec generator emits wrong controller names for multi-word controllers (blocker for typed surface).
- Upstream [`endavis/opnsense-openapi#33`](https://github.com/endavis/opnsense-openapi/issues/33): bug — misleading "No OpenAPI spec found" error when `openapi-python-client` is missing.
- Upstream [`endavis/opnsense-openapi#34`](https://github.com/endavis/opnsense-openapi/issues/34): refactor — stabilize generated-client module path across patch revisions; add closest-floor spec matching.
- Issue [#715](https://github.com/endavis/infrafoundry/issues/715): feat: spike + extend OPNsense gist-based `interface_assignments` write API (closed; PR [#716](https://github.com/endavis/infrafoundry/pull/716) merged 2026-05-02). Load-bearing evidence for this amendment.
- Issue [#717](https://github.com/endavis/infrafoundry/issues/717): chore: amend ADR-0014 to record gist-based REST mechanism for `interface_assignments` (this amendment).
- Production conversion of `OPNsenseDirectRunner.apply()` for `interface_assignments` from no-op to live — to be filed after this amendment merges; carries out gates (2) and (3).

## Related Documentation

- [`docs/development/opnsense-spike-vlan-findings.md`](../development/opnsense-spike-vlan-findings.md) — load-bearing evidence cited throughout this ADR.
- [ADR-0010: Protocol-Based Runner Interfaces](0010-protocol-based-runner-interfaces.md) — the contract `OPNsenseDirectRunner` implements.
- [ADR-0013: OPNsense Full-IaC Migration](0013-opnsense-full-iac-migration.md) — the deferral this ADR closes (lands when PR [#704](https://github.com/endavis/infrafoundry/pull/704) merges).
- [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../development/opnsense-spike-interface-assignment-gist-findings.md) — load-bearing evidence cited by the 2026-05-03 amendment.
