# ADR-0013: OPNsense Full-IaC Migration Coverage

**Date:** 2026-04-30
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

## Data model

YAML resource schemas mirror the [browningluke/opnsense](https://registry.terraform.io/providers/browningluke/opnsense/latest/docs) Terraform provider's resource arguments. New components follow the existing pattern: a Pydantic config model whose fields match the corresponding `opnsense_*` Terraform resource, rendered to `.tf` via Jinja2 (see `templates/opnsense/vlans.tf.j2` for the established shape).

`config migrate` extractors read live state from the OPNsense REST API via the `opnsense_openapi` client and write YAML in that same schema. The round-trip property `extract → apply` must converge: dumping a configured box and applying the dump back produces no drift.

The XML `config.xml` format is not part of either path. It is used only for one-shot scoping (e.g., the inventory in [docs/development/opnsense-resource-coverage.md](../development/opnsense-resource-coverage.md)) and as a fallback discovery aid for resource types where no stable API endpoint exists. When XML is required for a fallback, that decision is made per-component and recorded in the component's issue.

## Implementation order

1. `interface_assignments` — gates everything that depends on physical NIC mapping.
2. `nat_rules`.
3. `gateways` and `static_routes`.
4. `virtual_ips`.
5. Unbound extensions (`domain_override`, `host_alias`, `forward`).
6. `config migrate` extractors for the full set, in any order once each component lands.
7. Migration cutover (operator-facing): run extractors against the current box, remap NICs in YAML, switch endpoint, plan, apply.

Each step above is a separate feature issue. Issue numbers will be added to this ADR's **Related Issues** list as they're filed.

## Related Issues

- Issue [#701](https://github.com/endavis/infrafoundry/issues/701): Scope OPNsense full-IaC migration (this ADR)

## Related Documentation

- [OPNsense Provider Resource Coverage](../development/opnsense-resource-coverage.md) — current support matrix, gap list, and the box-to-box migration runbook template.
- [Implementing Providers](../development/implementing-providers.md) — pattern guide each new component will follow.
