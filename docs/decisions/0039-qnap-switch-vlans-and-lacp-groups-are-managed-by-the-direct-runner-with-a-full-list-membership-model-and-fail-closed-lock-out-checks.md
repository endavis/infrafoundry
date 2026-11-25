---
title: "ADR-0039: QNAP switch VLANs and LACP groups are managed by the direct runner with a full-list membership model and fail-closed lock-out checks"
description: The QNAP direct runner diffs and writes VLANs and LACP groups with full member lists, orders the writes in phases, refuses an end state that could cut the management connection, and reads the result back
date: 2026-11-25
audience:
  - contributors
tags:
  - adr
---

# ADR-0039: QNAP switch VLANs and LACP groups are managed by the direct runner with a full-list membership model and fail-closed lock-out checks

## Status

Accepted

**Amended:** 2026-11-25 (#1675) - the direct runner also manages `port` settings (decision 10), and decision 11 records their verification state.

## Context

ADR-0038 added the `qnap` provider with a report-only runner and left the diff and apply of VLANs and LACP groups to issue #1671. The switch is managed over the web UI's JSON API, which the vendor does not document. A static read of the UI's code and of the shapes the `qnap-qsw-rest` collector stored showed:

- A VLAN has no name field and there is no separate PVID: a port's untagged membership is its native VLAN. There is no served `ports/config` endpoint.
- `PUT vlan` writes a VLAN's complete member list, not a delta. The UI keeps a port untagged in at most one VLAN by first writing the other VLANs without it.
- LACP groups are read and written under `lacp/group`; their interfaces are numbered from `lacp/info.StartIndex`.
- Nothing in the API says which port carries the operator's management traffic. A wrong change to the management VLAN's membership cuts the connection.

MikroTik solved the same problem with a diff, ordered phases and a fail-closed management-path check ([ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md)), with deletes under [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md).

## Decision

1. **The direct runner manages two config types.** `QnapRestRunner` diffs, orders and writes `vlan` (key `id`; fields `tagged`, `untagged`, `absent`) and `lacp.group` (key `group`; fields `mode`, `members`, `absent`). The YAML resource name is only a label: it is never written, because the switch has no VLAN name. A firmware-only environment still plans no changes and makes no configuration call.
2. **Membership lives inside the `vlan` resource.** The API writes a VLAN's whole member list in one call, and untagged uniqueness is a rule across VLANs, so each VLAN declares its own lists. A port is an integer or `lagN`, the interface `N + StartIndex` (taken from the UI's code, unverified).
3. **Declared lists replace, omitted lists are kept.** A declared `tagged` or `untagged` list is the complete set; an omitted list keeps the live set. A port that becomes untagged in one VLAN is stripped from every other VLAN that holds it untagged, unmanaged VLANs included, and the plan says so. Membership is a field, not a managed object, so ADR-0018 governs only whole `vlan` and `lacp.group` objects.
4. **VLAN 1 is declarable but never created or deleted.** `absent: true` on VLAN 1 is a schema error. The schema accepts ids 1-4000.
5. **Seven phases.** A: LACP creates; B: strip an untagged port from the VLAN that gives it away; C: VLAN creates; D: VLAN updates, the management VLAN last; E: LACP updates; F: VLAN deletes; G: LACP deletes. Every write carries the complete end-state list. A VLAN written in B and D collapses to one update outcome. Strips of undeclared VLANs write but are never recorded as managed.
6. **Fail-closed lock-out checks.** The management VLAN comes from `provider_settings.qnap.management_vlan`, else is inferred from a single enabled `ip/ipv4/interface` entry with a warning that it is unverified; if neither works and the plan writes, it refuses. `protected_ports` names the ports that carry management traffic. The plan refuses an end state that deletes the management VLAN, removes a protected port (or, without `protected_ports`, any live member) from it or flips its Tagged flag, puts a protected port into a LACP group, or deletes or shrinks a protected LAG. Deleting a LAG that a remaining VLAN still lists is always refused.
7. **An explicit override.** `allow_lockout_risk: true` turns the refusals about the management VLAN and protected ports into warnings; the plan prints a warning line while it is set and `infra doctor` warns. It is a settings key, not a core CLI flag, so no public CLI signature changes. MikroTik has none.
8. **Liveness and read-back after the writes.** Whether the steps succeeded or failed, apply polls the unauthenticated `/api/live` until `liveness_timeout` (default 60 s, range 10-600) runs out, then logs in again and reads `vlan` and `lacp/group`. A switch that does not answer fails the apply naming the completed steps; a re-read that differs from the planned end state fails it naming the object. This also verifies the write bodies on first use.
9. **No automatic backup.** The collector writes into the config repo under its own git flow; coupling apply to it would give apply a side effect there. The docs say to run `infra collect` before the first apply, and every failure message names it.
10. **Port settings are a third config type.** `port` (key `port`, a physical port number; fields `alias`, `shutdown`, `speed`, `duplex`, `flow_control`, `fec`, `mtu`) is a settings resource: it only ever updates, has no `absent`, and a row that leaves the YAML is released, never deleted. Only declared fields are compared and written; the write is `PUT portlist`, an array `[{"idx", "data"}]` where `data` is the port's whole live row with the edits applied, one step per port with the web UI's 60 s timeout, in phases H (settings) and I (a change that includes `mtu`) after everything else. The lock-out rules extend to the *watched* ports (`protected_ports` with `lagN` expanded, else the management VLAN's members): shutting one down, or changing its speed, duplex or FEC, is refused; any MTU change is refused because the MTU looks switch-wide. All are overridable with `allow_lockout_risk`. The web UI's FEC rule (at least two FEC-enabled ports) is a plan error. The read-back also reads `ports`, compares declared fields only and warns when an MTU write spread to undeclared ports. The same change makes `count_ports` ignore the LACP interface rows (`Type` `ieee8023ad`) that `GET ports` returns, which had let VLAN validation accept port numbers that do not exist.
11. **Writes verified only in part.** Every VLAN and LACP write and the LAG numbering are taken from the UI's code, and are written as bodies in one place so a live check can correct them. A maintainer-approved live check created an empty VLAN and deleted it: `POST vlan` worked as written; `DELETE vlan` needed `{"idx": ["<id>"]}` (a list of string keys, as the UI sends) instead of a scalar, and an empty VLAN reads back as `"val": null`. Both were corrected. `PUT vlan`, the `lacp/group` writes and the LAG numbering remain unverified. The `PUT portlist` body was traced from the UI's code and verified by a maintainer-approved live check that changed one port's `alias` and changed it back: the switch accepted it, the read-back passed and no other field changed. `shutdown`, `speed`/`duplex`, `flow_control` and `fec` are fields the UI edits but are unverified on a device; `mtu` is never edited by the UI, so whether the switch accepts it is unverified until the first apply.

## Rationale

- **Per-port resources:** rejected. Every port write would have to be gathered back into per-VLAN calls, and two port resources could claim one VLAN's list.
- **A separate ADR from 0038:** ADR-0038 covers the firmware report; the membership semantics, the lock-out model and the override are decisions in their own right, as ADR-0026 and ADR-0037 are for MikroTik.
- **Fail closed on an unknown management VLAN:** the API cannot tell which ports matter, so the plan asks the operator instead of guessing.

## Related Issues

- [#1675](https://github.com/endavis/infrafoundry/issues/1675) QNAP port settings
- [#1671](https://github.com/endavis/infrafoundry/issues/1671) QNAP VLAN, port and LACP management
- [#1669](https://github.com/endavis/infrafoundry/issues/1669) QNAP provider with firmware tracking
- [#1670](https://github.com/endavis/infrafoundry/issues/1670) QNAP collector

## Related Documentation

- [QNAP provider](../providers/qnap.md)
- [Device config collectors](../guides/device-config-collectors.md)
- [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md) direct runners delete only what they applied
- [ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md) MikroTik management
- [ADR-0038](0038-qnap-switches-are-managed-over-the-web-uis-json-api-with-firmware-upgraded-by-a-provider-command.md) QNAP provider and firmware
