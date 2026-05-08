# ADR-0014: OPNsense Direct-API Apply Mechanism

**Date:** 2026-04-30
**Amended:** 2026-05-03 (#717, PR #718) — added second internal write path for resources with no native REST CRUD; records `interface_assignments` per-component decision
**Amended:** 2026-05-03 (#720, PR #N) — Gates (2) and (3) cleared; production conversion of `interface_assignments` from no-op to live complete (full CRUD via the in-tree `AssignSettingsController.php` fork at `src/infrafoundry/providers/opnsense/extensions/interface_assignments/`). Spike deleted.
**Amended:** 2026-05-04 (#722) — `static_routes` per-component decision recorded (stock direct-REST against `routes/routes/*route`; natural-key identity tuple `(network, gateway)`)
**Amended:** 2026-05-04 (#724) — `unbound_host_alias` and `unbound_forward` per-component decisions recorded (stock direct-REST against `unbound/settings/*`; natural-key identities; reconfigure via `unbound/service/reconfigure`; no controller fork)
**Amended:** 2026-05-04 (#723) — `virtual_ips` per-component decision recorded (stock direct-REST against `interfaces/vip_settings/*`; natural-key tuple identity `(interface, mode, address, vhid)`); secrets-handling subsection added covering `secret://env_secrets/...` URI resolution at apply time by `EnvSecretsBackend` (first direct-API consumer: CARP `password`)
**Amended:** 2026-05-04 (#725) — `port_forward` per-component decision recorded (stock direct-REST against `firewall/d_nat/*`; extends `nat_rules` with a third `kind`; identical mechanism to outbound and 1:1; no new wire mechanism)
**Amended:** 2026-05-04 (#726) — §8 resolved: pluggable extractor registry replaces per-component dispatch on the provider and CLI; new components are reachable via `config migrate` as soon as they register an extractor
**Amended:** 2026-05-05 (#742) — `firewall_rules` per-component decision recorded (stock direct-REST against the MVC `firewall/filter/*` controller; identity scheme matches `nat_rules`; legacy terraform path retired in the same PR — no `kind: legacy` shim). See ADR-0015 for the full driving decision.
**Amended:** 2026-05-05 (#746) — identity-marker bootstrap mechanism amended: shared, thread-safe helper (`services/_category_marker.py`) replaces per-service-lazy lookup. Closes a theoretical race between concurrent `firewall_rules` and `nat_rules` first apply against a fresh box (OPNsense `addItem` is not idempotent by category name). The "Per-component decisions" section gets a new "Marker bootstrap" entry; no per-component decisions change.
**Amended:** 2026-05-05 (#741) — runtime credential resolution amended: a shared helper (`services/_credentials.py`) lets operators override `api_url` / `api_key` / `api_secret` / `verify_ssl` via `OPNSENSE_*` env vars, gated by `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`. Both direct-API construction sites (`BaseService.from_environment` and the Kea-DHCP path in `OPNsenseProvider`) delegate to the helper. §"Secrets handling" gets a new "Runtime credential resolution" subsection; no per-component decisions change. Equivalent override paths for the terraform write path (`build_terraform_env_vars` in `core/provider_mixins.py`) and other providers are tracked as separate follow-ups.
**Amended:** 2026-05-06 (#758) — `kea_dhcp6` per-component decision recorded (stock direct-REST against the existing `kea/dhcpv6/*` controller, now driven by `KeaDHCPv6SubnetManager` and `KeaDHCPv6ReservationManager` on `OPNsenseDirectRunner` instead of the legacy `OPNsenseProvider._generate_kea_dhcp6_resources` path that ran under `generate_terraform()`). Adds a new "Finalization hooks" subsection describing a generic runner facility for end-of-apply work shared across managers (e.g., a single Kea reconfigure for both subnets and reservations). Reservation→subnet UUID resolution now raises `ReferenceValidationError` on a missing live subnet rather than silently skipping with a warning — a behavioral upgrade.
**Amended:** 2026-05-07 (#775) — `firewall_alias` per-component decision recorded (stock direct-REST against `firewall/alias/*` controller; natural-key identity = alias `name` (OPNsense-enforced unique); no controller fork; reconfigure via `firewall/alias/reconfigure`). The legacy terraform write path (`browningluke/opnsense` + `aliases.tf.j2`) is retired in the same PR — no `kind: legacy` shim. Mirrors #724's pattern for `unbound_host_alias`.
**Amended:** 2026-05-07 (#776) — `unbound_host_override` per-component decision recorded (stock direct-REST against `unbound/settings/HostOverride*`; natural-key identity = `(hostname, domain, rr)`; shared `unbound_reconfigure` finalization hook now coalesces across `unbound_host_alias`, `unbound_forward`, and `unbound_host_override`). Mirrors #724's pattern; legacy terraform path retired in same PR.
**Amended:** 2026-05-08 (#777, #778) — `kea_dhcp4` per-component decision recorded (stock direct-REST against the existing `kea/dhcpv4/*` controller, now driven by `KeaDHCPv4SubnetManager` and `KeaDHCPv4ReservationManager` on `OPNsenseDirectRunner` instead of the legacy terraform write path via `browningluke/opnsense`). Finalization hook key renamed from `kea_dhcp6_reconfigure` to `kea_reconfigure` and shared across all four Kea managers (DHCPv4 + DHCPv6, subnet + reservation). After this amendment, `dhcp_static_maps` is the only OPNsense component still on the terraform write path — closes the cutover-unblock series for OPNsense (companion: #775 firewall_alias, #776 unbound_host_override, #758 kea_dhcp6).
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

**Pluggable extractor registry keyed by `(provider_name, resource_type)`.** The registry lives in [`src/infrafoundry/core/extractors.py`](../../src/infrafoundry/core/extractors.py) and is shaped like `RunnerRegistry`: a class-based registry plus a module-level singleton with thin convenience functions. Providers populate it during their own `__init__` by registering one `Extractor` (anything with `extract(env_name, **kwargs) -> str`) per migratable component. The CLI `config migrate` command looks up extractors at runtime and validates `--provider` / `--component` against the registered set — no `click.Choice` edit is required when adding a new component.

The original 2026-04-30 form of this decision (per-component method on the provider, hardcoded to the CLI's choice list) was a deliberate deferral while the per-component shape settled in #711–#725. With ten components in flight that each followed the `migrate(env_name, **kwargs) -> str` contract, the dispatch became mechanical and the duplication was the larger cost. #726 carried out the resolution. The pre-#726 `OPNsenseProvider.migrate_<resource>` methods are retained as deprecated shims for one minor version; new callers should use `get_extractor("opnsense", "<resource_type>").extract(env_name)` directly.

**Breaking CLI rename:** the two pre-#726 component names — `kea/dhcp` and `isc-to-kea` — are now `kea_dhcp` and `isc_to_kea` (Python-identifier form, matching the registry key). No transparent alias.

See [`docs/development/implementing-providers.md`](../development/implementing-providers.md#registering-extractors-for-config-migrate) for the registration pattern.

### 9. Migration of existing Terraform-based paths

**Phased migration to direct-API as part of ADR-0013's implementation phase.** Net-new components from ADR-0013's list (`interface_assignments`, NAT rules, gateways, static routes, virtual IPs, Unbound extensions) ship under direct-API immediately. Existing Terraform-based paths migrate in priority order:

1. **VLANs** — the spike code is the seed; first to land.
2. `aliases`, `firewall_rules`, `unbound_host_override`.
3. `kea_subnet` / `kea_reservation` / `dhcp_static_maps` (these already use the OPNsense REST API directly via `opnsense_openapi`; the work is normalizing them onto `OPNsenseDirectRunner`).

The `templates/opnsense/playbook.yml.j2` Ansible service-reload playbook retires once the last Terraform-based component is gone.

> **Note (interface_assignments, #711, amended 2026-05-03):** OPNsense `26.1.6_2` exposes no REST CRUD for `<interfaces>`. The component shipped read-only in PR #712 (`list` / `migrate` / validation work; `apply` / `destroy` are loud no-ops). The write path is decided in this ADR's "Per-component decisions" section: server-side-validated REST via a forked, in-tree PHP controller (PR #716 spike). Production conversion (`OPNsenseDirectRunner.apply()` from no-op to live for this resource) was carried out in #720, which cleared gates (2) and (3) recorded above.

## Per-component decisions

Each new write mechanism that diverges from §1's default (REST via `opnsense_openapi`) is recorded here.

### `interface_assignments` (PR #716, 2026-05-02 spike; production conversion completed in #720, 2026-05-03)

**Mechanism:** Server-side-validated REST via the forked `AssignSettingsController.php` controller installed at `/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/`.

- **Read side:** `interfaces/overview/interfacesInfo` (already in production from PR #712, no controller required).
- **Write side:** `assign_settings/{addItem, setItem, getItem, searchItem, delItem}` against the installed controller.
- **Fork location:** graduated in #720 to `src/infrafoundry/providers/opnsense/extensions/interface_assignments/AssignSettingsController.php`. The spike directory `tools/spikes/interface_assignment_gist_rest/` was deleted in the same PR. Provenance and security-review summary live alongside at `src/infrafoundry/providers/opnsense/extensions/interface_assignments/PROVENANCE.md`.
- **Patches/extensions over the upstream gist:** `sessionClose()` removed (modern-OPNsense compatibility), IPv6 fields, `setItem` / `getItem` / `searchItem`, optional explicit `name: optN`, validation helpers. ~225 LoC net-new on top of ~345 LoC inherited from szymczag's BSD-2-Clause base.

**Rollback strategy:** No transactional rollback (option (c) from the findings doc).

The spike empirically established that `/api/core/backup/{backups,download}` returns HTTP 404 on `26.1.6_2`, so the original auto-rollback design is unavailable on this OPNsense version. Three options surfaced; this ADR adopts (c) for the following reasons:

- **Per-call server-side validation is the primary safety net.** Every `addItem`/`setItem`/`delItem` POST flows through OPNsense's standard `Config::getInstance()->save()`. Bad input (invalid IPv4, unknown `ipv4Type`, missing `device`) is rejected with HTTP 400 *before* any state change. The spike verified all three cases live.
- **OPNsense's auto-snapshot is the residual safety net.** `Config::save()` captures a pre-write snapshot in `/conf/backup/` (visible in System → Configuration → Backups in the GUI). Operators can manually revert from there for the "correct-but-undesired apply" case that validation can't catch.
- **Option (a) is wishful** — no alternative snapshot endpoint surfaced during the spike's REST probe.
- **Option (b) re-introduces SSH** into the safety path for rollback. The gist-based mechanism's premise was to remove SSH from the steady-state apply path; reusing it for rollback erodes that win. Rejected.

**Preconditions for production conversion** (cleared in #720, recorded here for the historical record):

- **Gate (2) — cleared in #720:** Empirically confirmed that an `addItem`/`setItem`/`delItem` REST call produces a new entry in System → Configuration → Backups (auto-snapshot) AND System → Log Files → System General (audit log). The PHP controller calls OPNsense's standard `Config::save()` write path; both fire. Operator-captured screenshots from the `opnsense-a` (26.1.6_2) live integration test live in PR #720's body.
- **Gate (3) — cleared in #720:** Security review of the ~225 LoC of net-new PHP in the forked controller completed. Findings: no privilege-escalation, injection, or filesystem-write surface introduced beyond the upstream gist's own surface. Full write-up in [`src/infrafoundry/providers/opnsense/extensions/interface_assignments/PROVENANCE.md`](../../src/infrafoundry/providers/opnsense/extensions/interface_assignments/PROVENANCE.md) ("Security review summary"); the bullets are also quoted inline in PR #720's body. BSD-2-Clause is compatible.

**Cross-reference:** [ADR-0013 §"Per-component decisions recorded so far"](0013-opnsense-full-iac-migration.md#per-component-decisions-recorded-so-far) updated to reflect this resolution. See also [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../development/opnsense-spike-interface-assignment-gist-findings.md) for the load-bearing evidence.

### `static_routes` (#722, 2026-05-04)

**Mechanism:** Stock direct-REST against the `routes/routes/*route` controller — no controller fork required (this component falls under §1's default).

- **Endpoints:** `POST routes/routes/searchroute` (list), `GET routes/routes/getroute/<uuid>` (full record under `{"route": {...}}` envelope, with `gateway` rendered as a select option dict), `POST routes/routes/addroute` and `POST routes/routes/setroute/<uuid>` (body envelope `{"route": {...}}`), `POST routes/routes/delroute/<uuid>`, `POST routes/routes/reconfigure`.
- **Identity:** natural key tuple `(network, gateway)`. OPNsense exposes no server-unique `name` field on routes; the operator-facing YAML `name` is metadata only (used for cross-resource references and `ResourceOutcome` addressing) and never travels on the wire. Two routes with the same `(network, gateway)` tuple are the same record by the diff engine. Updating either field is a delete + add (the diff engine emits both); updating only `descr` or `disabled` is an in-place `setroute` (preserves UUID).
- **Wire schema:** `network` (CIDR), `gateway` (next-hop gateway name), `descr` (operator description), `disabled` (`"0"`/`"1"` string). The probe (live on `opnsense-a` running `26.1.6_2`, 2026-05-04) confirmed those four fields plus the auto-assigned `uuid` exhaust the schema — no metric / mtu / interface override knobs exist on this OPNsense version.
- **Gateway reference scope:** validator accepts both managed `gateways` resources declared in YAML *and* live system gateways (e.g., `WAN_DHCP`, `WAN_DHCP6`) returned by `searchGateway`. Mirrors the gateway validator's interface-acceptance pattern — operators can route through dynamic gateways without first declaring them as managed.
- **Cross-protocol enforcement:** the live API empirically does *not* always reject an IPv4 CIDR routed through an IPv6 gateway (the probe accepted `203.0.113.0/24` → `WAN_DHCP6` without error), so the validator enforces the family match before the request lands. For managed gateways the protocol is read from YAML; for live system gateways the heuristic is the trailing-`6` convention (e.g., `WAN_DHCP6` → IPv6).
- **No description-suffix tag** and **no `infrafoundry` category bootstrap** (routes have no categories). Different from `nat_rules` (which uses suffix tags because firewall rules have no stable name field) and same as `gateways` (which has a server-unique `name` field).

**Rollback strategy:** Same as the rest of §1's default mechanism — rely on per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` (System → Configuration → Backups) is the residual safety net. No transactional rollback (option (c) from the `interface_assignments` rollback discussion applies fleet-wide for direct-REST mechanisms).

### `unbound_host_alias` (#724, 2026-05-04)

**Mechanism:** Stock direct-REST against the `unbound/settings/*HostAlias` controller — no controller fork required (this component falls under §1's default).

- **Endpoints:** `POST unbound/settings/searchHostAlias` (list), `GET unbound/settings/getHostAlias/<uuid>` (full record under `{"alias": {...}}` envelope, with `host` rendered as a select option dict mapping parent override UUID to `{"value": "...", "selected": 0|1}`), `POST unbound/settings/addHostAlias` and `POST unbound/settings/setHostAlias/<uuid>` (body envelope `{"alias": {...}}`), `POST unbound/settings/delHostAlias/<uuid>`, `POST unbound/service/reconfigure` (verb shared across the entire Unbound module).
- **Identity:** natural key tuple `(host_uuid, hostname)` at the wire — OPNsense keys aliases by parent host_override UUID and the alias hostname. The operator-facing YAML uses `(host_name, hostname)` where `host_name` is a managed `unbound_host_override` resource name *or* a live override identifier (`hostname` or `hostname.domain` form). The component manager resolves `host_name` → parent UUID at apply time by reading `searchHostOverride` rows; if no live override matches, `ReferenceValidationError` is raised at plan time.
- **Wire schema:** `host` (parent override UUID), `hostname` (alias label), `domain` (parent override's domain), `enabled` (`"0"`/`"1"` string), `description` (free-form). The probe (live on `opnsense-a` running `26.1.6_2`, 2026-05-04) confirmed those five fields plus the auto-assigned `uuid` exhaust the schema.
- **Cross-reference scope:** validator accepts both managed `unbound_host_override` resources declared in YAML *and* live overrides returned by `searchHostOverride`. Mirrors the static-route validator's gateway-acceptance pattern — operators can attach aliases to overrides that are still Terraform-managed (the existing `unbound_host_override` is currently Terraform-only) without first migrating them.
- **No description-suffix tag** and **no `infrafoundry` category bootstrap** (Unbound resources have no category surface). The natural-key tuple is sufficient for identity.

**Rollback strategy:** Same as the rest of §1's default mechanism — rely on per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### `unbound_forward` (#724, 2026-05-04)

**Mechanism:** Stock direct-REST against the `unbound/settings/*Forward` controller — no controller fork required (this component falls under §1's default).

- **Endpoints:** `POST unbound/settings/searchForward` (list), `GET unbound/settings/getForward/<uuid>` (full record under `{"dot": {...}}` envelope — note: the envelope key is `dot` regardless of `type` value, empirically confirmed by probe), `POST unbound/settings/addForward` and `POST unbound/settings/setForward/<uuid>` (body envelope `{"dot": {...}}`), `POST unbound/settings/delForward/<uuid>`, `POST unbound/service/reconfigure`.
- **Identity:** natural key tuple `(type, domain, server, port)`. Including `type` (forward / dot) in the key allows DoT and plain forwarders to coexist for the same domain/server/port — a common dual-resolver setup. The operator-facing YAML `name` is metadata only and never travels on the wire.
- **Wire schema:** `type` (select: `forward` / `dot`), `domain` (empty = global forwarder; non-empty = per-domain forwarder, what the GUI calls "domain override"), `server` (IPv4 or IPv6 address), `port` (default `"53"`), `verify` (CN to verify when `type=dot`), `forward_tcp_upstream` (bool string), `forward_first` (bool string), `enabled` (bool string), `description`. Field names match the wire format verbatim (no YAML aliases): `verify` not `verify_cn`; `forward_tcp_upstream` not `forward_tls_upstream` — the original issue body's sketch was wrong; the live probe is the authority.
- **Domain-override merge:** OPNsense merges what the GUI calls "Domain Override" and "Forwarder" into this single `Forward` resource — there is no separate `unbound_domain_override` REST surface. A `Forward` entry with `type=forward, domain="example.com"` is a domain forwarder; with `domain=""` it is a global forwarder. Recorded in ADR-0013's implementation order #5 amendment.
- **No description-suffix tag** and **no `infrafoundry` category bootstrap`**.

**Rollback strategy:** Same as the rest of §1's default mechanism.

### `virtual_ips` (#723, 2026-05-04)

**Mechanism:** Stock direct-REST against the `interfaces/vip_settings/*` controller — no controller fork required (this component falls under §1's default).

- **Endpoints:** `POST interfaces/vip_settings/searchItem` (list / dataTable rows), `GET interfaces/vip_settings/getItem/<uuid>` (full record under `{"vip": {...}}` envelope, with `interface` / `mode` / `gateway` rendered as select option dicts), `POST interfaces/vip_settings/addItem` and `POST interfaces/vip_settings/setItem/<uuid>` (body envelope `{"vip": {...}}`), `POST interfaces/vip_settings/delItem/<uuid>`, `POST interfaces/vip_settings/reconfigure` (verb shared across all VIP resources). The auxiliary `GET interfaces/vip_settings/getUnusedVhid` and `GET diagnostics/interface/CarpStatus` endpoints are surfaced by the live API but not used by this component.
- **Identity:** natural key tuple `(interface, mode, address, vhid)`. Including `mode` and `vhid` in the key allows multiple CARP VIPs to coexist on the same interface+address with different `vhid`s (a common dual-CARP setup) and distinguishes ipalias from CARP at the same IP. `vhid` is the empty string for non-CARP modes. The operator-facing YAML `name` is metadata only and never travels on the wire.
- **Wire schema:** `interface` (option-dict), `mode` (option-dict; `ipalias` / `carp` / `proxyarp`), `address` (the IP), `network` (CIDR mask as a string, e.g. `"24"` or `"64"`), `descr` (operator description; YAML-side alias `description`), `vhid_txt` (display-only; never written). Mode-specific fields: ipalias adds `gateway` / `noexpand` / `nobind`; carp adds `vhid` / `password` / `advbase` / `advskew` / `peer` / `peer6` / `nosync`. The probe (live on `opnsense-a` running `26.1.6_2`, 2026-05-04) confirmed those fields exhaust the schema. The issue body's `subnet: 24` sketch and `alias|carp|proxyarp|other` mode list were both wrong — the probe is authoritative.
- **Cross-resource ref:** `interface` validates against managed `interface_assignments` resources declared in YAML *and* live overview interfaces returned by `interfaces/overview/*`. Mirrors the nat_rule validator's interface-acceptance pattern.
- **Secret-bearing field:** CARP `password` accepts a `secret://env_secrets/<dotted/path>` URI in YAML. Resolution happens at apply time inside the component manager (see "Secrets handling" below); the service layer receives plaintext only and stays unaware of secrets. This is the first direct-API resource to carry a secret, and adds the new `EnvSecretsBackend`.
- **No description-suffix tag** and **no `infrafoundry` category bootstrap** (VIPs have no category surface; the natural-key tuple is sufficient for identity).

**Rollback strategy:** Same as the rest of §1's default mechanism — rely on per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### `port_forward` (#725, 2026-05-04)

**Mechanism:** Stock direct-REST against the `firewall/d_nat/*` controller (the OPNsense stock `DNatController` extending `FilterBaseController`) — no controller fork required (this component falls under §1's default). Extends `nat_rules` (#713) with a third `kind`; identical mechanism to outbound and 1:1.

- **Endpoints:** `POST firewall/d_nat/searchRule` (list), `GET firewall/d_nat/getRule/<uuid>`, `POST firewall/d_nat/addRule` and `POST firewall/d_nat/setRule/<uuid>` (body envelope `{"rule": {...}}`), `POST firewall/d_nat/delRule/<uuid>`, `POST firewall/d_nat/apply`. All standard verbs return 200 (`searchRule`, `getRule`, `addRule`, `setRule`, `delRule`, `apply`, `savepoint`, `toggleRule`, `moveRuleBefore`).
- **URL note:** snake-case routing — `DNatController` → `firewall/d_nat`, NOT `firewall/dnat` (concatenated). The original 2026-05-03 probe used the concatenated form, got 404, and incorrectly concluded the controller was absent. The 2026-05-04 re-probe of `opnsense-a` running `26.1.6_2` confirmed the controller ships stock at the snake-case URL.
- **Identity:** description-suffix `[infrafoundry:<name>]` + `infrafoundry` category, identical to outbound and 1:1 (#713). Per-kind diff isolation via the existing `(kind, name)` diff key — an outbound `foo` and a port_forward `foo` are independent identities.
- **Wire schema:** `disabled` (negative polarity vs operator-facing `enabled`), `log`, `sequence`, `interface`, `ipprotocol`, `protocol`, `source.network` / `source.port` / `source.not` (dotted, NOT the underscore-flattened forms used by outbound + 1:1), `destination.network` / `destination.port` / `destination.not`, `target` (redirect destination — same wire field as outbound's source-NAT translation target but different operator-facing semantics; documented in the `NATRuleConfig` docstring), `local-port` (hyphenated wire key; `local_port` in YAML and dataclass), `nordr` ("no rdr" / deny match), `pass` (Python keyword; `pass_action` in YAML/dataclass; values `""` / `"pass"` / `"rule"` — note: `"pass"` injects an implicit OPNsense filter rule that bypasses any companion `firewall_rules` declaration), `poolopts` (closed set: `""` / `round-robin` / `round-robin sticky-address` / `random` / `random sticky-address` / `source-hash` / `bitmask`), `natreflection` (closed set: `""` / `"purenat"` / `"disable"` — different keyword set than 1:1 which uses `""` / `"enable"` / `"disable"`), `tag`, `tagged`, `nosync`, `descr` (NOT `description` — DNat schema uses the abbreviated form; outbound + 1:1 use `description`).
- **Server-managed fields not exposed:** `created.*`, `updated.*`, `categories` index (managed via the `infrafoundry` category bootstrap), `associated-rule-id` (OPNsense uses this internally to link port_forward to its companion filter rule when `pass_action: "pass"` / `"rule"`; the DNat model docstring marks the field for removal in a future OPNsense version, so InfraFoundry never touches it — `pass_action` is the operator-facing knob).

**Rollback strategy:** Same as the rest of §1's default mechanism.

### `firewall_rules` (#742, 2026-05-05)

**Mechanism:** Stock direct-REST against the OPNsense MVC stateful filter controller `firewall/filter/*` — no controller fork required (this component falls under §1's default). See [ADR-0015](0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md) for the full per-component decision (controller choice, field coverage, identity scheme, migration story).

- **Endpoints:** `POST firewall/filter/searchRule`, `GET firewall/filter/getRule[/<uuid>]`, `POST firewall/filter/addRule`, `POST firewall/filter/setRule/<uuid>`, `POST firewall/filter/delRule/<uuid>`, `POST firewall/filter/toggleRule/<uuid>/<enabled>`, `POST firewall/filter/apply`, `POST firewall/filter/savepoint`. All eight verbs confirmed live on `opnsense-a` running `26.1.6_2`.
- **Identity:** description-suffix `[infrafoundry:<name>]` + `infrafoundry` category UUID — same scheme as `nat_rules` (#713). The MVC `categories` field is multi-valued (vs legacy single `<category>`), so the identity marker is **appended** to operator-supplied categories, not overwriting them; operator-set categories survive across applies.
- **Wire schema:** ~50 scalar / enum fields covering the full MVC `getRule` template (per [ADR-0015 §"Field coverage"](0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md#field-coverage)); `sched`, `shaper1`, `shaper2` punted to follow-up issues (require resources we don't manage yet). Fields with hyphens or dots in the wire key (`state-policy`, `divert-to`, `max-src-conn`, `max-src-conn-rate`, `set-prio`, `set-prio-low`, `udp-first`, `udp-multiple`, `udp-single`, etc.) use Python-identifier YAML/dataclass aliases mapped via a module-level `_PAYLOAD_FIELD_MAP` table.
- **Coexistence with terraform path:** retired in the implementation PR — no `kind: legacy` shim. The legacy `firewall_rules.tf.j2` template, `_generate_firewall_rules_terraform`, and the old `FirewallValidator` (alias-only) are deleted in the same commit; `endavis-infra` has zero terraform-managed firewall rules and no other consuming repo was identified at PR-review time.

**Rollback strategy:** Same as the rest of §1's default mechanism — per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. `firewall/filter/savepoint` is exposed on the service for manual rollback (15-revision retention) but is not auto-wired into apply.

### `unbound_host_override` (#776, 2026-05-07)

**Mechanism:** Stock direct-REST against the `unbound/settings/*HostOverride` controller — no controller fork required (this component falls under §1's default). Mirrors #724's pattern for `unbound_host_alias` and the same controller family; the read-side `migrate` extractor (#748) is preserved unchanged.

- **Endpoints:** `POST unbound/settings/searchHostOverride` (list / dataTable rows; defensive against non-dict responses), `GET unbound/settings/getHostOverride/<uuid>` (full record under `{"host": {...}}` envelope), `POST unbound/settings/addHostOverride` and `POST unbound/settings/setHostOverride/<uuid>` (body envelope `{"host": {...}}`), `POST unbound/settings/delHostOverride/<uuid>`, `POST unbound/service/reconfigure` (verb shared across the entire Unbound module).
- **Identity:** natural key tuple `(hostname, domain, rr)`. Including `rr` in the tuple lets an A and an AAAA record on the same `(hostname, domain)` coexist as distinct identities (a common dual-stack setup) — same shape `unbound_forward` uses to permit DoT and plain forwarders to coexist on the same domain/server. The operator-facing top-level YAML `name` is metadata only and never travels on the wire. Updating `hostname` / `domain` / `rr` is a delete + add (the diff engine emits both); updating only `server` / `description` / `enabled` / `mxprio` / `mx` is an in-place `setHostOverride` (preserves UUID).
- **Wire schema:** `hostname`, `domain`, `rr` (`A` / `AAAA` / `MX`), `server` (IPv4 for A, IPv6 for AAAA, commonly absent on MX), `description`, `enabled` (`"0"` / `"1"` string), `mxprio` (MX records only — preserved as a string to retain numeric precision; mirrors `updatefreq` handling on aliases), `mx` (MX records only). Wire field names are OPNsense's own (`rr` / `mxprio` / `mx`) — NOT the legacy terraform schema's `type` / `mx_priority` / `mx_host` (#765/#766 schema-compliance fix). The YAML schema is unchanged from #748 — operators continue to write `rr` / `mxprio` / `mx` in YAML.
- **Reconfigure coalescing:** `UnboundHostOverrideManager`, `UnboundHostAliasManager`, and `UnboundForwardManager` all declare `FINALIZATION_HOOK = "unbound_reconfigure"`. The runner coalesces hook keys per apply, so a multi-unbound apply produces exactly one `unbound/service/reconfigure` call instead of up to three (matches the pre-migration behavior — the terraform path produced one Ansible-driven reconfigure per apply). See "Finalization hooks" below.
- **Coexistence with terraform path:** retired in the implementation PR — no `kind: legacy` shim. The legacy `unbound_host_override.tf.j2` template, `_generate_unbound_host_override_terraform`, and `test_unbound_host_override.py` regression test are deleted in the same commit; matches #742's and #775's single-PR retirement pattern. The read-side `migrate` extractor (#748) is preserved unchanged — `foundry config migrate --component unbound_host_override` keeps working against the same `UnboundHostOverrideService.export_to_yaml`.
- **No description-suffix tag** and **no `infrafoundry` category bootstrap`**. The natural-key tuple is sufficient for identity (Unbound resources have no category surface).

**Rollback strategy:** Same as the rest of §1's default mechanism — per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### `firewall_alias` (#775, 2026-05-07)

**Mechanism:** Stock direct-REST against the `firewall/alias/*` controller — no controller fork required (this component falls under §1's default). Mirrors the #724 pattern for `unbound_host_alias`: a single controller, single endpoint family, no per-kind dispatch.

- **Endpoints:** `POST firewall/alias/searchItem` (list / dataTable rows; defensive against non-dict responses), `GET firewall/alias/getItem/<uuid>` (full record under `{"alias": {...}}` envelope), `POST firewall/alias/addItem` and `POST firewall/alias/setItem/<uuid>` (body envelope `{"alias": {...}}`), `POST firewall/alias/delItem/<uuid>`, `POST firewall/alias/reconfigure` (typed response `{"status": "ok"|"failed"}`). All confirmed live on `opnsense-a` running `26.1.6_2`.
- **Identity:** natural key = alias `name` (OPNsense-enforced unique server-side). The operator-facing top-level YAML `name` and `config.name` agree on extraction (the migrate output writes both identically); operators may rename the top-level name freely after import — the diff engine uses `config.name` (the wire identity) as the diff key. Updating `name` is a delete + add; updating any other field is an in-place `setItem` (preserves UUID).
- **System-alias filtering:** `type: internal` (per-interface auto-generated network aliases like `__lan_network`) and `type: external` (system-managed tables like `bogons` / `sshlockout` / `virusprot`) are silently filtered from both `export_to_yaml` output and the diff engine's view of live state. OPNsense regenerates these server-side; including them would produce spurious "delete" entries the operator can neither write nor remove.
- **Wire schema:** `name`, `type`, `description`, `content` (newline-joined string on the wire, list in YAML), `enabled` (`"0"` / `"1"` string), `proto` (geoip only — `IPv4` / `IPv6`), `updatefreq` (urltable / urltable_ports — preserved as a string to retain decimal precision), `categories` (selected-dict on read; comma-separated string on write), `counters` (`"0"` / `"1"` string), `interface` (dynipv6host only). Type-specific fields are emitted to YAML only when the live record carries a non-default value, so existing operator YAML round-trips identically.
- **Coexistence with terraform path:** retired in the implementation PR — no `kind: legacy` shim. The legacy `aliases.tf.j2` template, `_generate_aliases_terraform`, and `test_aliases_template.py` regression test are deleted in the same commit; matches #742's single-PR retirement pattern. The read-side `migrate` extractor (#747) is preserved unchanged — `foundry config migrate --component aliases` keeps working against the same `AliasService.export_to_yaml`.
- **No description-suffix tag** and **no `infrafoundry` category bootstrap**. The natural-key `name` is sufficient for identity (unlike `firewall_rules` and `nat_rules`, which lack a stable name field and need the suffix-tag scheme).

**Rollback strategy:** Same as the rest of §1's default mechanism — per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### `kea_dhcp6` — subnets and reservations (#758, 2026-05-06)

**Mechanism:** Stock direct-REST against the existing `kea/dhcpv6/*` controller — no controller fork required (this component falls under §1's default). The wire surface is unchanged from the pre-#758 path; what changes is *where* mutation happens: two new component managers (`KeaDHCPv6SubnetManager`, `KeaDHCPv6ReservationManager`) drive `OPNsenseDirectRunner` instead of the inline `OPNsenseProvider._generate_kea_dhcp6_resources` path that ran under `generate_terraform()`.

- **Endpoints:** `GET kea/dhcpv6/searchSubnet` / `getSubnet/<uuid>` / `addSubnet` / `setSubnet/<uuid>` / `delSubnet/<uuid>`, mirrored for reservations. `kea/service/reconfigure` triggers via the runner's finalization hook (see "Finalization hooks" below). All operations confirmed live on OPNsense `25.7.11_1` and `26.1.6_2` per the prior #757 / #756 work.
- **Identity:** subnets are keyed by the natural `subnet` CIDR (operator YAML `subnet:` field; e.g., `fd00:1::/64`). Reservations are keyed by the `(duid, subnet_uuid)` tuple — same scheme the legacy path used. The reservation manager resolves `subnet` (a CIDR in YAML) → live subnet UUID at plan/apply time via `service.search_dhcpv6_subnets()`.
- **Reservation→subnet reference scope:** the resolver raises `ReferenceValidationError` if the YAML CIDR has no live match, surfacing typos at plan time rather than silently skipping the reservation with a warning at apply time. This is a deliberate behavioral upgrade over the legacy path.
- **Change-detection helpers:** the `_extract_*` / `_build_desired_*` / `_drop_non_round_trip_subnet_fields` / `_log_field_diff` / `_select_option_dict_value` / `_normalize_field_value` helpers (originally added in PR #757 for #756) live at module scope in `src/infrafoundry/providers/opnsense/services/kea_dhcp.py`. The asymmetric `valid_lifetime` and option-dict normalization fixes from #757 survive intact (relocation, not rewrite).
- **`add_only`:** both managers honor the `--add-only` runner flag (a behavioral gain — the legacy path had no concept of `add_only`).
- **Path-B over Path-A:** the alternative was to add a runner-level "post-apply pass" contract specifically for the kea reconfigure. Path B (manager split + reusable finalization hook) was chosen because the subnet/reservation managers fall cleanly into the existing nine-component dispatch table, the finalization-hook mechanism generalizes (future components with shared post-apply work can reuse it), and the runner contract stays simpler (one `apply()` body, opt-in hook attribute on the manager class).

**Rollback strategy:** Same as the rest of §1's default mechanism — per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### `kea_dhcp4` — subnets and reservations (#777, #778, 2026-05-08)

**Mechanism:** Stock direct-REST against the existing `kea/dhcpv4/*` controller — no controller fork required (this component falls under §1's default). Mirrors #758's pattern for `kea_dhcp6`: two new component managers (`KeaDHCPv4SubnetManager`, `KeaDHCPv4ReservationManager`) drive `OPNsenseDirectRunner` instead of the legacy terraform write path via `browningluke/opnsense` (`opnsense_kea_subnet`, `opnsense_kea_reservation`). The legacy templates `kea_subnet.tf.j2` / `kea_reservation.tf.j2`, the `_generate_kea_subnet_terraform` / `_generate_kea_reservation_terraform` provider methods, and the corresponding entries in `get_terraform_resource_types()` are retired in the same PR — no `kind: legacy` shim. After this PR, `dhcp_static_maps` is the only OPNsense component still on the terraform write path.

- **Endpoints:** `GET kea/dhcpv4/searchSubnet` / `getSubnet/<uuid>` / `addSubnet` / `setSubnet/<uuid>` / `delSubnet/<uuid>`, mirrored for reservations. `kea/service/reconfigure` triggers via the runner's finalization hook (see "Finalization hooks" below). The `KeaClient._crud_*` helpers (originally hardcoded to `kea/dhcpv6/`) gained an `api_version: str` parameter so DHCPv4 and DHCPv6 share the same plumbing.
- **Identity:** subnets are keyed by the natural `subnet` CIDR (operator YAML `subnet:` field; e.g., `10.0.10.0/24`). Reservations are keyed by the `(hw_address, subnet_uuid)` tuple — DHCPv4 uses MAC address as the client identity (distinct from DHCPv6's `duid`). The reservation manager resolves `subnet` (a CIDR in YAML) → live subnet UUID at plan/apply time via `service.search_dhcpv4_subnets()`.
- **Reservation→subnet reference scope:** the resolver raises `ReferenceValidationError` if the YAML CIDR has no live match, surfacing typos at plan time. Mirrors the DHCPv6 manager's behavior — a behavioral upgrade over the legacy terraform path which would silently break the terraform graph dependency on a box-to-box cutover (the boxes have different subnet UUIDs).
- **Wire-schema differences from DHCPv6:**
  - DHCPv4 uses **flat** `option_data_*` fields (e.g., `option_data_dns_servers`, `option_data_routers`, `option_data_domain_name`, `option_data_ntp_servers`, `option_data_domain_search`, `option_data_autocollect`) rather than nested under an `option_data` dict like DHCPv6. Confirmed by reading `services/kea_dhcp.py:export_to_yaml` which already round-tripped these fields read-side.
  - DHCPv4 add/update subnet envelope key is `"subnet4"` (parallel to DHCPv6's `"subnet6"`); reservation envelope is `"reservation"` (same as DHCPv6).
- **Change-detection helpers:** new `_extract_subnet4_fields` / `_build_desired_subnet4_fields` / `_extract_reservation4_fields` / `_build_desired_reservation4_fields` / `_drop_non_round_trip_subnet4_fields` helpers live at module scope in `services/kea_dhcp.py` alongside their DHCPv6 counterparts. Reuses the existing `_log_field_diff` / `_normalize_field_value` / `_select_option_dict_value` helpers (no DHCPv4-specific variants needed — the option-dict shape is the same).
- **`add_only`:** both managers honor the `--add-only` runner flag (a behavioral gain — the legacy terraform path had no concept of `add_only`).
- **Cutover-regression cases:** the 2026-05-08 prod cutover plan listed 7 DNS/NTP-only changes on existing subnets (drift on `option_data_dns_servers` / `option_data_ntp_servers`) and 1 description-only change on the `qnap` reservation. The diff engine detects each as an in-place update (preserving UUIDs) rather than a delete+add cycle. Verified by dedicated unit-test cases.
- **Path-B over Path-A:** same trade-off as #758. Path B (manager split + shared `kea_reconfigure` finalization hook) chosen because the DHCPv4 managers slot cleanly into the existing dispatch table and reuse the same hook the DHCPv6 managers already declared.

**Rollback strategy:** Same as the rest of §1's default mechanism — per-call server-side validation; OPNsense's auto-snapshot in `/conf/backup/` is the residual safety net. No transactional rollback.

### Finalization hooks (runner facility, #758)

`OPNsenseDirectRunner.apply()` exposes a generic end-of-apply hook mechanism so component managers can defer work that must run **after** every component has applied (instead of running it in each manager's own `apply` body, which would double-fire on shared-resource operations like a Kea reconfigure).

The contract is opt-in on both sides and graceful in absence:

1. **Manager side (opt-in):** A component manager class declares an optional class-level attribute `FINALIZATION_HOOK: ClassVar[str] = "<key>"`. Managers that don't declare it are unaffected.
2. **Provider side (opt-in):** A provider exposes an optional method `get_finalization_hooks(self) -> dict[str, Callable[[str], None]]` returning hook callables keyed by string. Providers that don't implement it are a graceful no-op (the runner falls back to skipping the hook firing).
3. **Runner side (mandatory plumbing):** During `apply()`, the runner tracks per-type "had_changes" booleans (sum of created/updated/deleted > 0) and collects the `FINALIZATION_HOOK` value of every manager that mutated state. The collected set is deduped, then each unique key resolves to a hook callable via `provider.get_finalization_hooks()`. Each callable is invoked exactly once with `env_name`. Hook errors propagate so a failing post-apply step (e.g., reconfigure) fails the apply loud.
4. **Contract scope:** Hooks fire on `apply` only. `plan` and `destroy` skip the hook firing entirely — `plan` never mutates, and `destroy` is a separate operational mode where the operator explicitly opts into per-component teardown semantics.

The first registered hook is `kea_reconfigure`, declared on all four Kea managers — `KeaDHCPv4SubnetManager`, `KeaDHCPv4ReservationManager`, `KeaDHCPv6SubnetManager`, and `KeaDHCPv6ReservationManager` — resolved by `OPNsenseProvider.get_finalization_hooks()` to a closure that calls `KeaDHCPService.reconfigure()`. Subnet and reservation changes across both wire families that land in the same `apply` share a single Kea reconfigure firing — preserving the legacy "one reconfigure per plan/apply" operational behavior. The hook key was originally `kea_dhcp6_reconfigure` when introduced in #758 (DHCPv6 only); it was renamed to `kea_reconfigure` in #777/#778 when DHCPv4 was migrated to direct-API and joined the same hook (the OPNsense `kea/service/reconfigure` endpoint is shared between v4 and v6).

A second hook, `unbound_reconfigure` (#776), is declared on all three Unbound managers — `UnboundHostOverrideManager`, `UnboundHostAliasManager`, and `UnboundForwardManager`. The OPNsense Unbound service's reconfigure verb (`unbound/service/reconfigure`) is shared across every Unbound-managed component, so coalescing the hook key across all three managers produces exactly one reconfigure call per apply when any of the three changed state. Before #776 each manager called `service.reconfigure()` inline from its `apply` body, which produced up to three reconfigure calls in a multi-unbound apply; the retrofit removes the inline calls and lets the runner's hook plumbing coalesce them. Future components with shared post-apply work register their own key here.

### Marker bootstrap (#746, amended 2026-05-05)

The `infrafoundry` category UUID is resolved via a shared, thread-safe helper (`src/infrafoundry/providers/opnsense/services/_category_marker.py`) rather than per-service lazy lookup. The helper holds a process-local cache keyed by OPNsense client `base_url` and serializes the search+create critical section under a `threading.Lock`. This closes a theoretical race that would surface if `OPNsenseDirectRunner.apply()` ever dispatched components concurrently — `addItem` is not idempotent by category name on OPNsense's side, so two concurrent first-apply dispatches would create two distinct `infrafoundry` rows. The runner's responsibility is unchanged; the fix lives entirely in the service layer.

Both `FirewallRuleService._ensure_infrafoundry_category` and `NATRuleService._ensure_infrafoundry_category` are now thin wrappers that delegate to the helper. Each service keeps its per-instance `_category_uuid` cache as a fast-path so an instance that already resolved the UUID does not pay even the helper's dict-lookup cost on subsequent calls.

## Secrets handling

Direct-API resources can declare secret-bearing fields as `secret://env_secrets/<dotted/path>` URIs in YAML. Resolution is performed at apply time by the component manager, which:

1. Constructs a `SecretResolver` and registers an `EnvSecretsBackend` initialized from `env_config.secrets` (the in-memory dict produced by SOPS decryption of `envs/<env>/secrets.yaml`).
2. Walks each managed resource's `config` dict via `resolver.resolve_config()` to expand `secret://...` URIs to their plaintext values.
3. Passes the resolved configs to the service layer, which sees plaintext only and stays unaware of secrets.

The validator (plan-time) accepts `secret://...` URIs as a valid placeholder without resolving — resolution is strictly an apply-time concern. Plaintext values in secret-bearing fields are accepted but produce a soft warning so operators don't silently commit secrets to YAML.

**First consumer:** `virtual_ips` (CARP `password`, #723).

**Future-proofing:** if a follow-up direct-API resource needs secrets, that issue is the place to consolidate this pattern (e.g., generalize to runner-level pre-resolution rather than per-component manager). The current component-manager-level resolution is the smallest viable path.

### Runtime credential resolution (#741, 2026-05-05)

OPNsense client credentials (`api_url`, `api_key`, `api_secret`, `verify_ssl`) are resolved at apply time by the shared helper `src/infrafoundry/providers/opnsense/services/_credentials.py`. Both direct-API construction sites — `BaseService.from_environment` (every direct-API service) and the Kea-DHCP path in `OPNsenseProvider` — delegate to `resolve_credentials(provider_settings)` rather than reading `provider_settings.opnsense` directly.

**Precedence (gated):** when `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE` is set to a truthy value (anything not in `("", "0", "false", "no", "off")`, case-insensitive), each field resolves env-FIRST: a non-empty `OPNSENSE_API_URL` / `OPNSENSE_API_KEY` / `OPNSENSE_API_SECRET` / `OPNSENSE_VERIFY_SSL` env var wins, otherwise the corresponding `provider_settings` key is used. Empty string and unset are treated identically (fall back to settings). When the gate is unset (or falsy), behavior is unchanged from before — env vars are not consulted.

**Why opt-in:** the gate prevents a forgotten direnv shell from silently mass-applying to the wrong box. An operator who exports `OPNSENSE_API_URL` for one shell session and forgets to unset it would otherwise have the next `foundry infra apply --env prod` redirect to the staging mirror (or the reverse) without warning. The gate makes the override explicit-per-shell rather than ambient.

**`OPNSENSE_VERIFY_SSL` parsing** matches the project convention from `tests/integration/opnsense/test_vlan_live.py`: any value not in `("0", "false", "no", "off")` (case-insensitive after `.strip().lower()`) is true. Empty/unset falls back to the settings value.

**Endpoint-redirect warning:** when the gate is active and the resolved `api_url` differs from `provider_settings.get("api_url")`, the helper emits a single WARNING-level log record naming the resolved URL. The warning is one-time per process per resolved URL — a single `infra plan` invocation that constructs multiple services produces one warning, not one per service. Override that does not change the URL (e.g., gate set with only `OPNSENSE_API_KEY` overridden) emits no warning, since there is no endpoint redirect to flag.

**Operator ergonomic:** the runbook in [`opnsense-resource-coverage.md`](../development/opnsense-resource-coverage.md#box-to-box-migration-runbook-template) documents the env-var-override variant of step 5 ("Switch endpoint") for one-shot operator-driven cutover without editing the SOPS-encrypted `settings.yaml`.

**Out of scope (follow-ups):** the equivalent override path for the terraform write path lives in `core/provider_mixins.py:build_terraform_env_vars`, which today reads `provider_settings` only — same gap. The same pattern for other providers (proxmox, oci) is not done. Both are tracked as separate per-subsystem issues; the issue body's claim that the terraform path already honors env vars was incorrect.

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
- Issue [#720](https://github.com/endavis/infrafoundry/issues/720): feat: convert `OPNsenseDirectRunner.apply()` for `interface_assignments` from no-op to live. Carries out gates (2) and (3); recorded as cleared in the 2026-05-03 amendment line above and in the per-component decisions section.
- Issue [#722](https://github.com/endavis/infrafoundry/issues/722): feat: add OPNsense `static_routes` component (direct-API, natural-key tuple identity).
- Issue [#723](https://github.com/endavis/infrafoundry/issues/723): feat: add OPNsense `virtual_ips` component (direct-API, natural-key tuple identity `(interface, mode, address, vhid)`; first direct-API resource with secrets — CARP `password` via `secret://env_secrets/...` URIs and the new `EnvSecretsBackend`).
- Issue [#724](https://github.com/endavis/infrafoundry/issues/724): feat: add OPNsense Unbound extensions — `unbound_host_alias` and `unbound_forward` (direct-API; merges domain_override into forward per live probe).
- Issue [#725](https://github.com/endavis/infrafoundry/issues/725): feat: add OPNsense `port_forward` kind on `nat_rules` (direct-API at `firewall/d_nat`; closes ADR-0013 implementation-order item #2; the 2026-05-04 re-probe corrected the original deferral premise).
- Issue [#726](https://github.com/endavis/infrafoundry/issues/726): refactor: extract `config migrate` extractor registry from per-component dispatch (resolves §8; breaking CLI rename `kea/dhcp` → `kea_dhcp` and `isc-to-kea` → `isc_to_kea`).
- Issue [#746](https://github.com/endavis/infrafoundry/issues/746): bug — identity-marker race condition between concurrent `firewall_rules` and `nat_rules` first apply (closed by the shared-helper bootstrap recorded under "Marker bootstrap" above).
- Issue [#741](https://github.com/endavis/infrafoundry/issues/741): feat — env-var override for OPNsense direct-API runtime credentials. Adds the shared `services/_credentials.py` helper, the `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE` gate, and the endpoint-redirect warning recorded under "Runtime credential resolution" above.
- Issue [#758](https://github.com/endavis/infrafoundry/issues/758): refactor — move `kea_dhcp6` management off `generate_terraform()` onto `OPNsenseDirectRunner` via two new component managers + a reusable finalization-hook runner facility. Recorded under "Per-component decisions" / `kea_dhcp6` and "Finalization hooks" above.
- Issue [#775](https://github.com/endavis/infrafoundry/issues/775): feat: migrate `firewall_alias` write path from terraform to direct-API (`firewall/alias/*` controller; natural-key identity = alias `name`; legacy terraform path retired in the same PR — no `kind: legacy` shim). Recorded under "Per-component decisions" / `firewall_alias` above.
- Issue [#776](https://github.com/endavis/infrafoundry/issues/776): feat: migrate `unbound_host_override` write path from terraform to direct-API (`unbound/settings/*HostOverride` controller; natural-key identity = `(hostname, domain, rr)`; shared `unbound_reconfigure` finalization hook coalesces across host_override / host_alias / forward; legacy terraform path retired in the same PR — no `kind: legacy` shim). Recorded under "Per-component decisions" / `unbound_host_override` and "Finalization hooks" above.
- Issue [#777](https://github.com/endavis/infrafoundry/issues/777): feat: migrate `kea_subnet` (DHCPv4) write path from terraform to direct-API (paired with #778). Recorded under "Per-component decisions" / `kea_dhcp4` and "Finalization hooks" above.
- Issue [#778](https://github.com/endavis/infrafoundry/issues/778): feat: migrate `kea_reservation` (DHCPv4) write path from terraform to direct-API (paired with #777; identity tuple `(hw_address, subnet_uuid)`; reservation→subnet UUID resolution raises `ReferenceValidationError` on missing live subnet). Recorded under "Per-component decisions" / `kea_dhcp4` above.

## Related Documentation

- [`docs/development/opnsense-spike-vlan-findings.md`](../development/opnsense-spike-vlan-findings.md) — load-bearing evidence cited throughout this ADR.
- [ADR-0010: Protocol-Based Runner Interfaces](0010-protocol-based-runner-interfaces.md) — the contract `OPNsenseDirectRunner` implements.
- [ADR-0013: OPNsense Full-IaC Migration](0013-opnsense-full-iac-migration.md) — the deferral this ADR closes (lands when PR [#704](https://github.com/endavis/infrafoundry/pull/704) merges).
- [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../development/opnsense-spike-interface-assignment-gist-findings.md) — load-bearing evidence cited by the 2026-05-03 amendment.
