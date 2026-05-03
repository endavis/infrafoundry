# ADR-0013: OPNsense Full-IaC Migration Coverage

**Date:** 2026-04-30
**Amended:** 2026-05-03 (#717) — `interface_assignments` per-component decision updated; cross-reference to ADR-0014's new Per-component decisions section
**Status:** Accepted
**Issue:** [#701](https://github.com/endavis/infrafoundry/issues/701)

## Context

The OPNsense provider currently manages a subset of `config.xml`: VLANs, aliases, firewall rules, Kea DHCP (v4/v6 subnets and reservations), Unbound host overrides, and legacy ISC DHCP static maps. Everything else — interface assignments, NAT, gateways, static routes, virtual IPs, the rest of Unbound (domain override, host alias, forward) — lives only in the running box's `config.xml` and cannot be reproduced by `foundry infra apply` against a fresh box.

A planned cutover (replace one OPNsense host with same-spec successors) surfaced this as a blocker: the operator wants to dump current state to YAML, change the endpoint, and re-apply on the new box. With today's coverage, that workflow recreates only DHCP and Unbound host overrides; everything else has to be hand-built or imported from `config.xml` on the new box, which defeats the goal of a repeatable IaC migration.

## Decision

We will close the IaC gap so OPNsense box-to-box migration is achievable through `foundry infra apply`, with a clearly bounded set of items deliberately left to manual `config.xml` import.

**In scope (new components, one feature issue per row):**

| Resource type | Reason |
| --- | --- |
| `interface_assignments` | The remap point when physical NIC names differ between boxes; blocks placement of VLANs and firewall rules. |
| `nat_rules` | Outbound + port forward + 1:1 — required for any non-trivial WAN setup. |
| `gateways` | Required for multi-WAN, policy routing, and gateway groups. |
| `static_routes` | Needed when downstream networks aren't reachable via the default route. |
| `virtual_ips` | Required for CARP, NAT outbound source addresses, and IP aliases. |
| Unbound `domain_override`, `host_alias`, `forward` | Existing `unbound_host_override` is incomplete — host aliases and conditional forwarders are common in real deployments. |

**Tooling work:**

- `config migrate` extractors for every supported and newly-added resource type, extending the pattern that today exists only for Kea DHCP. Without these, dumping state from a live box requires writing API queries by hand.

**Out of scope (manual `config.xml` selective import on the target box):**

| Section | Reason |
| --- | --- |
| `<hasync>` | Set-once HA pairing config. |
| `<openvpn>`, `<OPNsense>/OpenVPN` | Typically one or two clients/servers per box; pinning structure into IaC is high cost, low value. |
| `<ca>`, `<cert>`, `<OPNsense>/AcmeClient` | Certificate material; importing is faster and safer than re-issuing through IaC. |
| `<gres>`, `<gifs>`, `<laggs>`, `<bridges>`, `<ppps>`, `<wireless>` | Each typically a single record per box; not worth a component. |

ISC DHCP (`<dhcpd>`/`<dhcpdv6>`) is also out of scope going forward — Kea is the supported path and the existing ISC→Kea helper covers the migration when needed.

## Rationale

- **Drop-in replacement is the operator's stated goal.** The current Kea-only coverage doesn't get there.
- **Interface assignment is the lever that makes hardware swaps repeatable.** Without it, every cutover requires hand-editing `config.xml` interface mappings on the target. With it, hardware-identical successor boxes are a "change endpoint, re-apply" operation.
- **The deferred items are deliberately small and stable.** HA sync, OpenVPN, ACME, certs, and physical layer constructs (LAGG/bridge/GRE/etc.) change infrequently and are well-served by OPNsense's selective `config.xml` import. Putting them under IaC is a future option, not a prerequisite.
- **The scope is bounded and incremental.** Each gap is its own component with a clear contract (template + validator + manager + tests + `config migrate` extractor). Issues can ship independently and the migration runbook absorbs each one as it lands.

## Data model and apply mechanism

Decided in [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md): direct-API via `opnsense_openapi`. New components ship under that pattern; existing Terraform-based paths (`vlans`, `aliases`, `firewall_rules`, `unbound_host_override`, `kea_*`, `dhcp_static_maps`) migrate per-component in the order below, retiring the `templates/opnsense/playbook.yml.j2` Ansible service-reload step with the last one.

ADR-0014 takes positions on schema source, client surface, runner integration (a new `OPNsenseDirectRunner(BaseRunner)` implementing the [ADR-0010](0010-protocol-based-runner-interfaces.md) protocols), default semantics (fully-managed with `--add-only` opt-in), the `lock: true` resource-level safety annotation, and plan-time validation of interface references. Refer to that ADR for the rationale and the open follow-ups.

The XML `config.xml` format is not part of any apply or migrate path. It is used only for one-shot scoping (as in [docs/development/opnsense-resource-coverage.md](../development/opnsense-resource-coverage.md)) and remains a per-component fallback only if no stable API endpoint exists for a resource type. That decision would be made per-component and recorded in its issue.

### Per-component decisions recorded so far

- `interface_assignments` (#711, #715→PR #716, amended 2026-05-03 via #717): read-only / migrate shipped in PR #712 (`/api/interfaces/overview/*`). Write path adopts server-side-validated REST via the forked `AssignSettingsController.php` controller; the spike validated the mechanism end-to-end on `26.1.6_2`. See [ADR-0014 §"Per-component decisions"](0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions) for the mechanism details, the rollback decision (option (c) — no transactional rollback; rely on per-call server-side validation + OPNsense auto-snapshot), and the gates remaining for production conversion.

## Implementation order

Each step ships under the direct-API pattern codified in [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md). The VLAN spike (PR [#706](https://github.com/endavis/infrafoundry/pull/706), merged) seeds the VLAN component migration.

1. `interface_assignments` — gates everything that depends on physical NIC mapping. *Read-only / migrate shipped in PR #712 (#711); write-path mechanism decided in ADR-0014 amendment (#717); production conversion gated on a follow-up issue that carries out gates (2) and (3).*
2. `nat_rules`.
3. `gateways` and `static_routes`.
4. `virtual_ips`.
5. Unbound extensions (`domain_override`, `host_alias`, `forward`).
6. `config migrate` extractors for the full set, in any order once each component lands.
7. Migration cutover (operator-facing): run extractors against the current box, remap NICs in YAML, switch endpoint, plan, apply.

Each step above is a separate feature issue. Issue numbers will be added to this ADR's **Related Issues** list as they're filed.

## Related Issues

- Issue [#701](https://github.com/endavis/infrafoundry/issues/701): Scope OPNsense full-IaC migration (this ADR).
- Issue [#705](https://github.com/endavis/infrafoundry/issues/705): VLAN direct-API spike that informed ADR-0014 (closed; PR [#706](https://github.com/endavis/infrafoundry/pull/706) merged).
- Issue [#707](https://github.com/endavis/infrafoundry/issues/707): ADR-0014 (closed; PR [#708](https://github.com/endavis/infrafoundry/pull/708) merged).
- Issue [#709](https://github.com/endavis/infrafoundry/issues/709): VLAN component direct-API migration (`OPNsenseDirectRunner` seed).
- Issue [#711](https://github.com/endavis/infrafoundry/issues/711): `interface_assignments` component (read-only / migrate; dispatch-table refactor).
- Issue [#715](https://github.com/endavis/infrafoundry/issues/715): gist-based `interface_assignments` write-API spike (closed; PR [#716](https://github.com/endavis/infrafoundry/pull/716) merged 2026-05-02).
- Issue [#717](https://github.com/endavis/infrafoundry/issues/717): chore: amend ADR-0014 to record the gist-based REST mechanism for `interface_assignments`.

## Related Documentation

- [ADR-0014: OPNsense Direct-API Apply Mechanism](0014-opnsense-direct-api-apply-mechanism.md) — codifies the apply mechanism this ADR's implementation phase uses.
- [OPNsense Provider Resource Coverage](../development/opnsense-resource-coverage.md) — current support matrix, gap list, and the box-to-box migration runbook template.
- [OPNsense Direct-API VLAN Spike Findings](../development/opnsense-spike-vlan-findings.md) — load-bearing evidence ADR-0014 cites.
- [Implementing Providers](../development/implementing-providers.md) — pattern guide each new component will follow.
