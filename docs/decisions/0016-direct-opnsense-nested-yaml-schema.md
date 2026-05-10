# ADR-0016: Direct-OPNsense Nested YAML Schema Convention

**Date:** 2026-05-08
**Amended:** 2026-05-10 (#806) — First production validation of the singleton structural-discrimination claim. Issue #806 ships seven `opnsense.system.*` dict-shape singletons (`hostname`, `dns`, `ssh`, `webgui`, `firmware`, `remotebackup`, `tuning`) under the nested namespace. The loader's `DOTTED_RESOURCE_SHAPES` map is extended for each; the new shared scaffolding `components/_singleton.py` (`SingletonDiff`, `diff_singleton`, `enforce_singleton`) is reusable for upcoming singletons in #786, #787, #788, #790, #791, #792. The `name: settings` sentinel pattern remains obviated as described in §"Schema shape — illustrative example".
**Status:** Accepted

## Status

Accepted

## Decision

The direct-OPNsense provider's YAML schema migrates from flat top-level resource type keys (e.g. `firewall_log:`, `tailscale_settings:`, `acmeclient_certs:`) to a **nested API-aligned hierarchy under a top-level `opnsense:` namespace**. Internal `ResourceConfig.type` strings rename to dotted paths matching the YAML hierarchy (e.g. `firewall.aliases`, `kea.dhcp4.subnets`). The provider dispatch table keys on the dotted strings.

This is a **provider-scoped** decision: only the direct-OPNsense provider is affected. The terraform write path (already retired for OPNsense per [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) §9), other providers (`esxi`, etc.), and InfraFoundry's filename-derived stem path for non-opnsense provider-centric configs are unchanged.

The YAML hierarchy mirrors OPNsense's API path tree (`/api/<plugin>/<surface>/<action>`), which is the implementation's structural truth. Operators who can read the API documentation (or the OpenAPI spec) can locate the matching YAML location by inspection.

### Schema shape — illustrative example

Flat (current):

```yaml
firewall_log:
  - name: high-noise-block
    config:
      enabled: false

tailscale_settings:
  enabled: true
  exit_node: false

kea_subnet:
  - name: lan
    config:
      subnet: 192.0.2.0/24
```

Nested (target):

```yaml
opnsense:
  firewall:
    log:
      enabled: false                       # singleton — leaf is a dict
    aliases:                               # list — leaf is a YAML sequence
      - name: trusted-hosts
        config:
          type: host
          content: ["192.0.2.10"]
  tailscale:
    settings:                              # singleton
      enabled: true
      exit_node: false
  kea:
    dhcp4:
      subnets:                             # list
        - name: lan
          config:
            subnet: 192.0.2.0/24
```

**Type discrimination is structural, not nominal.** A leaf-as-dict is a singleton; a leaf-as-sequence is a collection. No `name: settings` sentinel field is required to distinguish a singleton from a list — this **obviates the unfiled `name: settings` sentinel pattern** that was tentatively floated for #786 (firewall_log) before this ADR.

### Type rename mapping

The following starting-proposal table maps the current flat `ResourceConfig.type` strings to dotted paths. **Subject to API endpoint verification during Phase 1 implementation** — any cell that doesn't survive the live-API check is amended in this ADR before that PR merges.

| Current flat | Proposed dotted | Notes |
|---|---|---|
| `vlans` | `interfaces.vlans` | API: `/api/interfaces/vlan_settings/` |
| `interface_assignments` | `interfaces.assignments` | API: `/api/interfaces/overview/` + forked controller |
| `aliases` | `firewall.aliases` | API: `/api/firewall/alias/` |
| `nat_rules` | `firewall.nat` | three kinds (outbound, 1:1, port_forward) under one type |
| `firewall_rules` | `firewall.rules` | MVC controller |
| `gateways` | `routing.gateways` | API: `/api/routing/gateways/` |
| `static_routes` | `routing.static` | API: `/api/routes/routes/` |
| `virtual_ips` | `interfaces.virtual_ips` | operator-facing as interfaces; verify API path during Phase 1 |
| `unbound_host_override` | `unbound.host_overrides` | |
| `unbound_host_alias` | `unbound.host_aliases` | |
| `unbound_forward` | `unbound.forwards` | |
| `kea_subnet` | `kea.dhcp4.subnets` | |
| `kea_reservation` | `kea.dhcp4.reservations` | |
| `kea_dhcp6_subnet` | `kea.dhcp6.subnets` | |
| `kea_dhcp6_reservation` | `kea.dhcp6.reservations` | |

**Future singletons** from in-flight issues land at: `firewall.log` (#786), `tailscale.settings` / `tailscale.subnets` / `tailscale.auth` (#787), `radvd` (#788), `cron.jobs` (#789), `acmeclient.{settings,accounts,validations,certs,actions}` (#790), `monit.{settings,alerts,services,tests}` (#791), `hostwatch` (#792). Singleton vs list discrimination is structural per the Schema-shape section above.

### Cross-reference syntax

Cross-resource references (gateway lookups, alias targets, host_override targets, future acmeclient cert→account, etc.) accept three syntactic forms, resolved by a shared helper at `src/infrafoundry/providers/opnsense/validators/_xref.py`:

- `<name>` — relative within the validator's expected type (e.g. an account ref defaults to `acmeclient.accounts`)
- `<subkey>.<name>` — in-plugin relative (e.g. `accounts.le-prod`)
- `<plugin>.<sub>.<name>` — cross-plugin absolute (e.g. `cron.jobs.acmeclient-auto-renew`)

Resolution returns the matched `ResourceConfig` or `None`; on miss, the validator surfaces a `ValidationReport` error. Cross-plugin refs to plugins not yet loaded are deferred-warning rather than hard-fail (plugin discovery order varies).

### Migration strategy — hard cutover with transient shim

The cutover is **hard at merge of the final framework phase**: the flat-format provider-centric parse path for the opnsense provider is removed in lockstep with the operator-side conversion. There is **no permanent backward-compatibility shim**.

A **transient `STEM_TO_DOTTED` translation map** in the loader (added Phase 1, removed Phase 5) lets old flat YAML continue parsing through Phases 1–4 while internal type strings are already dotted. Nested-format support lands additively in Phase 2; flat is parsed and re-keyed via the shim. The shim is deleted in Phase 5 alongside the operator's one-shot conversion of the user's `endavis-infra/` config repo.

### Phasing — six framework phases plus operator conversion

Each phase ships as its own PR; each leaves `doit check` green; each is independently reviewable.

- **Phase 0 — ADR (this document).** Lock the convention before code lands. Single PR, docs only.
- **Phase 1 — Type rename + dispatch.** Internal `ResourceConfig.type` strings rename to dotted paths everywhere (~50 test files). Provider dispatch dict keys become dotted. Old flat YAML still parses via the temporary `STEM_TO_DOTTED` lookup. No schema change yet.
- **Phase 2 — Loader nested-format support (additive).** Loader gains a nested-parse branch that recognizes the `opnsense:` namespace key and walks the tree, emitting `ResourceConfig` with dotted `type`. Old flat format continues to work. New unit tests cover singleton-as-dict, list-as-sequence, deeply nested (`kea.dhcp4.subnets`), malformed leaves, unknown keys.
- **Phase 3 — Cross-reference resolution.** Shared dotted-path resolver in `validators/_xref.py`; loader exposes a per-env index keyed by dotted-type-path → `{name: ResourceConfig}` for O(1) lookup. Per-validator updates for gateway / alias / host_override target / future acmeclient cert→account refs.
- **Phase 4 — `migrate()` emits nested YAML.** Each of the 14 component managers' `migrate()` method emits nested YAML so `config migrate` produces output the new loader can read. Golden-file tests per component.
- **Phase 5 — Hard cutover.** Loader drops the flat-format provider-centric branch for the opnsense provider only; `STEM_TO_DOTTED` shim deleted; remaining test fixtures converted to nested. Lands in lockstep with Phase 6.
- **Phase 6 — `endavis-infra/` conversion (separate repo).** One-shot Python script under `endavis-infra/scripts/convert_to_nested_v1.py` (dry-run + apply modes; preserves Jinja2 expressions verbatim via regex; writes `.new.yaml` for operator review). Operator promotes `.new.yaml` → `.yaml`. Script committed alongside conversion output, deleted in follow-up commit.

## Rationale

1. **API alignment as the structural truth.** Every direct-OPNsense component is implemented against `/api/<plugin>/<surface>/<action>`. The flat schema forced manager-to-API mapping into the manager classes; the nested schema makes the mapping declarative in the YAML itself. Operators who read the OPNsense API documentation can locate the matching YAML location by inspection.

2. **Resolves the naming bikeshed surfaced during the #786–#792 walkthrough.** Variants like `_general`, `_settings`, `tailscale_settings:` vs `tailscale:` were repeatedly proposed and rejected because no single suffix worked across both singletons and lists. With nested + structural discrimination, the question disappears: `tailscale.settings` is a singleton dict, `tailscale.subnets` is a list, no suffix needed at the top level.

3. **Eliminates the wire-`<name>` field collision with YAML top-level identity slugs.** Several OPNsense resources (e.g. `interface_assignments` with explicit `name: optN`) carry a wire-level `name` field that conflicts with the YAML top-level identity slug. Under the nested schema, the YAML identity slug lives at the leaf-list element's `name:` key and doesn't compete for the same namespace as the wire `name`.

4. **Obviates the `name: settings` sentinel pattern.** A previously floated sentinel (use `name: settings` to distinguish a singleton from a list of one) collapsed under structural discrimination — leaf-as-dict is a singleton, leaf-as-sequence is a list.

5. **Hard cutover keeps the loader code path simple long-term.** A permanent shim would mean two parallel parse paths forever. The transient `STEM_TO_DOTTED` shim is bounded to Phases 1–4 and removed in Phase 5 in lockstep with the operator-side conversion.

6. **Provider-scoped scope keeps the blast radius bounded.** This is not a framework-wide schema change; it's a per-provider convention. The terraform path for OPNsense is already retired ([ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) §9), so the only consumers of the nested schema are the direct-API components.

## Risk Areas

1. **Mixed dict/list ambiguity at the same nested level.** Operator typo `firewall: {rules: {...}}` instead of `firewall: {rules: [...]}` would otherwise round-trip silently as a singleton. Loader inspects leaf shape against the provider's declared `get_direct_api_resource_shapes()` mapping (`{path: "list" | "dict"}`) and emits an error pointing at the dotted path on mismatch.

2. **Dotted-name collisions.** A resource named `letsencrypt.prod` would clash with the dotted-path syntax in cross-refs. Mitigation: forbid `.` in the resource `name` field at validation time (loader-level rule, applies to every dotted-keyed type).

3. **Singleton vs list ambiguity.** Resolved by explicit shape declaration via `OPNsenseProvider.get_direct_api_resource_shapes()`. Provider declares each dotted path as `"list"` or `"dict"`; loader rejects shape mismatches.

4. **Cross-plugin refs to plugins not yet loaded.** Plugin discovery order may not match referencing order. Resolution is deferred to *after* full env load, not during per-file parse — `_xref.py` runs against a fully-populated index. Unresolvable refs are deferred-warning, not hard-fail.

5. **Migrate output format drift.** Phase 4 golden-file tests prevent drift; `doit check` runs after every component update.

6. **Jinja2 in nested keys.** Loader's `_render_resource_file` already runs before structural parsing (existing behavior at `package_loader.py:412–422`); nested parsing happens on rendered YAML so Jinja expressions in keys round-trip correctly.

7. **Non-opnsense fixtures.** Phase 5 must remove the flat path *only* for the opnsense provider; esxi and other providers' filename-derived stem path (existing `STEM_TO_DOTTED`-free behavior at `package_loader.py:464`) stays unchanged.

## Affected in-flight issues

The following feature issues were drafted against the flat schema and require body revisions to the nested shape after this ADR merges. The body revisions are a **text-only follow-up task** (batch `gh issue edit`), **not part of this ADR's PR**:

| Issue | Resource | Nested location |
|---|---|---|
| [#786](https://github.com/endavis/infrafoundry/issues/786) | firewall_log | `opnsense.firewall.log` (singleton) |
| [#787](https://github.com/endavis/infrafoundry/issues/787) | tailscale | `opnsense.tailscale.{settings,subnets,auth}` |
| [#788](https://github.com/endavis/infrafoundry/issues/788) | radvd | `opnsense.radvd` (singleton; subshape verified Phase 1) |
| [#789](https://github.com/endavis/infrafoundry/issues/789) | cron_jobs | `opnsense.cron.jobs` (list) |
| [#790](https://github.com/endavis/infrafoundry/issues/790) | acmeclient | `opnsense.acmeclient.{settings,accounts,validations,certs,actions}` |
| [#791](https://github.com/endavis/infrafoundry/issues/791) | monit | `opnsense.monit.{settings,alerts,services,tests}` |
| [#792](https://github.com/endavis/infrafoundry/issues/792) | hostwatch | `opnsense.hostwatch` (singleton; subshape verified Phase 1) |

## Verification

Per-PR (Phases 1–5):

1. `doit check` — tests + lint + mypy + format + spelling
2. `doit coverage` — ≥69%
3. Targeted: `uv run pytest tests/unit/providers/opnsense/ tests/unit/core/config/`

End-to-end (after Phase 5 + Phase 6 conversion):

4. `cd endavis-infra && uv run foundry -c . infra plan --env prod` — full plan against converted real-world config; **expected: zero diff** vs pre-conversion plan baseline.
5. `infra plan --env prod -P opnsense` — identical resource list as pre-refactor.
6. Integration: `tests/integration/test_opnsense_nested_plan.py` against fixtures.

## Related Issues

- [#793](https://github.com/endavis/infrafoundry/issues/793) — driving issue for this ADR
- [#786](https://github.com/endavis/infrafoundry/issues/786), [#787](https://github.com/endavis/infrafoundry/issues/787), [#788](https://github.com/endavis/infrafoundry/issues/788), [#789](https://github.com/endavis/infrafoundry/issues/789), [#790](https://github.com/endavis/infrafoundry/issues/790), [#791](https://github.com/endavis/infrafoundry/issues/791), [#792](https://github.com/endavis/infrafoundry/issues/792) — in-flight feature issues whose YAML shape this ADR formalizes
- [ADR-0013](0013-opnsense-full-iac-migration.md) — full OPNsense IaC migration scope
- [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) — direct-API apply mechanism (sibling; this ADR formalizes the YAML schema convention that ADR-0014's per-component decisions plug into)
- [ADR-0015](0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md) — firewall_rules direct-API via MVC controller (per-component decision; consumes the nested schema)

## Related Documentation

- [`docs/development/opnsense-resource-coverage.md`](../development/opnsense-resource-coverage.md) — coverage matrix for direct-OPNsense components; the Phase-1+ implementation updates the matrix's YAML examples to nested form
