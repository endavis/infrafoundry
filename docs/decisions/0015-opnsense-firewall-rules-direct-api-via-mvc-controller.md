# ADR-0015: OPNsense firewall_rules direct-API via MVC controller

**Status:** Proposed

## Status

Proposed — pending review of [#742](https://github.com/endavis/infrafoundry/issues/742).

## Context

[ADR-0013](0013-opnsense-full-iac-migration.md) scoped the full OPNsense-IaC migration; [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) chose direct-API as the apply mechanism for new and migrated components. Every newer component (`vlans`, `interface_assignments`, `nat_rules`, `gateways`, `static_routes`, `virtual_ips`, `unbound_host_alias`, `unbound_forward`) ships under direct-API per ADR-0014.

`firewall_rules` is the remaining production-critical component still on the older terraform + `browningluke/opnsense` provider path. Issue [#742](https://github.com/endavis/infrafoundry/issues/742) documents that the current pipeline cannot express features prod actually uses — policy-based routing (`<gateway>`), floating rules, direction (in/out), `quick`, `statetype`, source/destination negation, `<any>`, and address-vs-network dest semantics — because those fields never round-trip through `firewall_rules.tf.j2`. A live audit of prod's `<filter>` block (82 rules) confirmed every gap is reached by real rules.

A live REST-surface survey of `opnsense-a` running `26.1.6_2` (2026-05-05) is captured at [`tmp/agents/claude/issue-742-firewall-survey.md`](../../tmp/agents/claude/issue-742-firewall-survey.md) as evidence; the relevant findings are folded into this ADR. The survey will not be committed — it is a working artifact.

## Decision

`firewall_rules` joins the direct-API ecosystem per ADR-0014. The wire surface is OPNsense's stock **MVC stateful filter controller at `firewall/filter/*`** — not the legacy `<filter>` block, and not extension via the `browningluke` terraform provider.

The implementation pattern is identical to `nat_rules` (PR #719 for outbound + 1:1; PR #725 for port_forward as a third `kind`):

- Stock REST against `firewall/filter/{searchRule, getRule, addRule, setRule/<uuid>, delRule/<uuid>, toggleRule/<uuid>/<enabled>, apply, savepoint}` (all confirmed live on `26.1.6_2` during the survey).
- Identity scheme: `<operator description> [infrafoundry:<name>]` suffix on `description`, plus the `infrafoundry` UUID in the rule's `categories` list as a fleet-wide marker so unmanaged rules are ignored by the diff.
- `categories` field is multi-valued in MVC (vs legacy's single `<category>`), so the identity marker can coexist with operator-set categories without collision.
- Reconfigure on apply via POST `firewall/filter/apply`.
- Transactional rollback via `firewall/filter/savepoint` (15-revision retention, same as the nat_rules pattern).

This is a **stock-REST direct-API decision**, in the sense of [ADR-0014 §1 "Apply mechanism for new components"](0014-opnsense-direct-api-apply-mechanism.md). No forked PHP controller is required. No SSH dependency for the apply path.

## Rationale

Three paths were considered. (C) below is the chosen one.

**(A) Extend `firewall_rules.tf.j2` (terraform / browningluke).**
Discarded. The browningluke provider's `opnsense_firewall_rule` resource caps the field surface; even a perfect Jinja template can't reach `<not>`, `<floating>` (legacy shape), or the full `gateway` cross-reference. Inconsistent with ADR-0014's direct-API trajectory and pulls a third-party dependency further into the critical path. Net debt.

**(B) Scrape the legacy `<filter>` PHP pages (`/firewall_rules.php?if=...`)** via the gist-based REST mechanism developed in PR #716 / #728 for `interface_assignments`.
Discarded. The legacy filter system is on OPNsense's deprecation track — the new GUI at `/ui/firewall/filter/` already exists and is being promoted as the forward path. Investing scrape infrastructure in a system upstream is moving away from would compound technical debt. The gist-based mechanism is reserved for resources that have **no REST surface at all** (per ADR-0014 §1) — `firewall_rules` has a clean MVC controller.

**(C) Direct-API to the MVC controller `firewall/filter/*`.** Chosen. Confirmed live on `26.1.6_2` with a 53-field surface that covers 100% of #742's table plus richer semantics in several cells (e.g., `direction=any` is new; `state-policy` and `statetype` distinguish flag families that the legacy system collapsed; `categories` is multi). The endpoint shape is the same `{search, get, add, set, del, toggle, apply, savepoint}` pattern InfraFoundry already implements for `nat_rules`, `gateways`, `static_routes`, `virtual_ips`, and the unbound resources, so the implementation is a straight adaptation of an existing pattern, not new ground.

## Field coverage

Cover every scalar / simple-enum field on the MVC `getRule` template at write time. The cost is one schema row per field; the value is being able to round-trip operator-set rules without lossy fallback.

| Category | Fields covered |
| --- | --- |
| Core / match | `action`, `enabled`, `description`, `sequence`, `sort_order`, `quick`, `interface`, `interfacenot`, `direction`, `ipprotocol`, `protocol`, `source_net`, `source_not`, `source_port`, `destination_net`, `destination_not`, `destination_port`, `log` |
| State | `statetype`, `state-policy`, `statetimeout`, `adaptivestart`, `adaptiveend` |
| Routing | `gateway`, `divert-to`, `replyto`, `disablereplyto` |
| Categorization | `categories` (multi), `tag`, `tagged` |
| ICMP / TCP | `icmptype`, `icmp6type`, `tcpflags1`, `tcpflags2`, `tcpflags_any` |
| Limits | `max`, `max-src-conn`, `max-src-conn-rate`, `max-src-conn-rates`, `max-src-nodes`, `max-src-states`, `overload` |
| QoS | `prio`, `prio_group`, `set-prio`, `set-prio-low`, `tos` |
| UDP / pfsync | `udp-first`, `udp-multiple`, `udp-single`, `nopfsync`, `nosync` |
| Misc | `allowopts` |

**Punted to follow-up issues** because they introduce new cross-resource models we don't manage yet:

- `sched` — would require a `schedules` resource type. Prod has 0 schedules; not blocking.
- `shaper1`, `shaper2` — would require a `traffic_shapers` resource type. Prod uses neither.

The field-set is finalized at ADR-acceptance time; new fields surfacing in later OPNsense versions are additive amendments.

## Cross-references and validation

- **`gateway`** field — value must resolve to either a managed `gateways` YAML resource or a live system gateway name (`WAN_DHCP`, `WAN_DHCP6`, `Null4`, `Null6`, etc.). Same pattern as `static_routes` ([ADR-0014](0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions) §`static_routes`).
- **`source_net` / `destination_net`** — accepts `any`, a CIDR, an IP, an alias name (managed in YAML or live), or an interface sentinel (`<iface>` / `<iface>net`). Validator confirms alias references resolve.
- **`categories`** — initially accepts UUIDs only. Operator-friendly category names (`firewall_categories` resource type with name → UUID resolution at apply time) is a follow-up issue.
- **`sched`** — accept the field but defer cross-reference validation; document that managed schedules are not yet supported.

## Identity and ownership

- **Identity (suffix-in-description, plus category marker)** matches `nat_rules`. Operators can edit a managed rule's description in the GUI **only after** the suffix tag (`[infrafoundry:<name>]`); editing or removing the suffix breaks identity parsing on the next plan and causes the rule to be re-created (drift behavior; the diff reports this clearly).
- **The `infrafoundry` category UUID** is a one-time setup item per box (provisioned alongside the runner's first apply on a box, via `firewall/category/addItem`). The UUID is stable per-box; the runner discovers and caches it.

## Migration story

OPNsense 26.x ships **two** independent firewall systems:

1. **Legacy** `<filter>` block in `config.xml`, rendered by classic `/firewall_rules.php` pages. This is where prod's 82 rules currently live (prod is on 25.x).
2. **MVC** `firewall/filter/*` (this ADR's target), with its own GUI at `/ui/firewall/filter/`.

The two systems do not auto-cross-populate. There is a GUI-only **migration page** at `/ui/firewall/migration` (the survey confirmed no REST surface — every probed `firewall/migration/*` URL returned 404). Migrating an existing legacy ruleset into MVC is therefore a **one-time operator GUI step**, comparable to the partial-config.xml restore of out-of-IaC sections during box-to-box cutover.

For the immediate use case driving #742 — mirroring prod to a freshly-built `opnsense-a` (26.1.6_2):

1. Author MVC YAML directly in InfraFoundry; apply against `opnsense-a` MVC. `opnsense-a` ships clean — no legacy rules to migrate from.
2. Prod stays on legacy unchanged until a separate cutover.
3. Eventual prod cutover: GUI migration of legacy → MVC, then prod becomes IaC-managed via the same direct-API path.

This sequence is added to [`docs/development/opnsense-resource-coverage.md`](../development/opnsense-resource-coverage.md) box-to-box runbook.

## Coexistence with the existing terraform path

Existing `firewall_rules.tf.j2` rendering and the validator's terraform-managed firewall rule path **stay callable** during the deprecation window. The provider dispatch table (`OPNsenseProvider.get_direct_api_resource_types()`) routes `firewall_rules` resources to the new component manager **by default**; envs that have terraform-managed firewall rules in state can opt back into the old path via `kind: legacy` on the resource (parallel to `nat_rules`'s `kind: outbound | one_to_one | port_forward`) for one minor-release window. Removal of the terraform path is a follow-up issue with its own migration note for affected envs.

If the PR-level review concludes there are no envs with terraform-managed `firewall_rules` worth carrying forward (the `endavis-infra` repo has 0; no other consuming repo is known), the `kind: legacy` shim can be dropped from the implementation and the terraform path retired in the same PR. Decide in the implementation PR.

## Implementation outline

Following the `nat_rules` template:

- `src/infrafoundry/providers/opnsense/services/firewall_rule.py` — service layer (search / get / add / set / del / toggle / apply / savepoint; identity parse and serialize).
- `src/infrafoundry/providers/opnsense/components/firewall_rule.py` — component manager (plan / apply / destroy / get_resource_ids / extract).
- `src/infrafoundry/providers/opnsense/__init__.py` — register direct-API dispatch entry; register extractor.
- `src/infrafoundry/providers/opnsense/validators/firewall_validator.py` — extend with gateway / categories / source-or-dest-alias / mutex enforcement.
- Pydantic schema for `config:` block covering the field set above.
- Tests: unit (service identity parsing + diff), integration (apply round-trip against a fake API), live-API marker (`@pytest.mark.live`) using `OPNSENSE_API_URL`.
- Update [`docs/development/opnsense-resource-coverage.md`](../development/opnsense-resource-coverage.md) matrix row for `firewall_rules` (mark direct-API; identity scheme; supported fields; deferred fields).

## Acceptance Criteria (mirrored to #742)

- [ ] All MVC fields in the table above representable in YAML and apply-able to a live 26.x box.
- [ ] Identity scheme matches `nat_rules` (`[infrafoundry:<name>]` suffix + `infrafoundry` category marker).
- [ ] Validators enforce `gateway`, alias, and source/destination mutex constraints.
- [ ] `foundry config migrate --component firewall_rules` produces apply-clean YAML round-trip against a live MVC ruleset (also closes #743's `firewall_rules` extractor row).
- [ ] `docs/development/opnsense-resource-coverage.md` updated.
- [ ] Migration note in the runbook for legacy → MVC.
- [ ] `kind: legacy` shim either implemented or retired (decision recorded in PR).

## References

- [#742](https://github.com/endavis/infrafoundry/issues/742) (this ADR's driving issue)
- [#743](https://github.com/endavis/infrafoundry/issues/743) (extractor for `firewall_rules` consolidates with the implementation PR for this ADR)
- [ADR-0013](0013-opnsense-full-iac-migration.md), [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md)
- [`docs/development/opnsense-resource-coverage.md`](../development/opnsense-resource-coverage.md)
- Survey artifact (transient): `tmp/agents/claude/issue-742-firewall-survey.md`

