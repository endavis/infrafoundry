---
title: "ADR-0038: QNAP switches are managed over the web UI's JSON API, with firmware upgraded by a provider command"
description: A QNAP switch is managed over its web UI's JSON API with a pinned certificate, and its firmware is upgraded by a provider command, not by apply
date: 2026-11-25
audience:
  - contributors
tags:
  - adr
---

# ADR-0038: QNAP switches are managed over the web UI's JSON API, with firmware upgraded by a provider command

## Status

Accepted

## Context

A QNAP QSW-M series switch has no Terraform provider, no SSH and no SNMP in the deployment this targets. Its only management surface is the web UI's JSON API under `/api/v1`, served over HTTPS with a self-signed certificate. The vendor does not document that API; it was read from the web UI's JavaScript bundle and from read-only probes of one switch. Issue #1669 asks for a provider that tracks the switch's firmware. VLAN and port management (#1671) and a configuration collector (#1670) follow later and should reuse the same client.

The same shape already exists for other devices: GL.iNet routers are upgraded through a provider command ([ADR-0036](0036-glinet-firmware-is-upgraded-through-the-vendor-online-upgrade-by-a-provider-command.md)) and MikroTik RouterOS through the plan-time update report plus a provider command ([ADR-0037](0037-mikrotik-routeros-is-upgraded-to-the-latest-release-of-a-channel-by-a-provider-command.md)). A firmware install reboots the device and cuts traffic, so it must not happen during `apply`.

## Decision

1. **A `qnap` provider manages one switch per environment.** Settings are `provider_settings.qnap` with `api_url` (https only), `username` and `password` (both `secret://` references), `tls_fingerprint` or, unsafely, `verify_ssl: false`, and three timeouts: `timeout` (every request, default 10 s), `check_timeout` (only the slow update check, default 90 s) and `upgrade_timeout` (default 1200 s).
2. **Resource type `firmware.update`.** The type name with `.` turned into `/` is the API path, as for `system.package.update` in ADR-0037. A bare `firmware` would read like OPNsense's `system.firmware`, which upgrades during apply. The resource has no fields, at most one per environment, and no version pinning: the switch follows the vendor's latest release.
3. **A report-only direct runner, `QnapRestRunner` (`qnap_rest`).** `plan` prints the provider's firmware lines through the `firmware_plan_lines` hook and reports no changes; `apply` and `destroy` succeed with zero counts. The generic `get_plan_notes` hook was rejected because it receives neither `add_only` nor `target_resources` and would ask the vendor on targeted plans that exclude the resource. The runner is also where the diff and apply of #1671 will go. The hook is skipped for add-only (drift) runs.
4. **Terraform is an empty stub.** `generate_terraform` is abstract and the Terraform runner runs for every provider, so the provider renders an empty `terraform {}` block, as MikroTik does.
5. **Certificate pinning.** The client pins the switch's certificate by its SHA-256 fingerprint, checked during the TLS handshake before any request byte is written. The shared implementation lives in `core/tls_pin.py`. Moving the GL.iNet client onto it is a separate follow-up refactor.
6. **No login retry.** A login is one `POST users/login`. Any refusal raises an authentication error and is never retried, because the switch's lockout behaviour is unknown: the web UI shows only "Invalid username or password." and no lockout message, and the vendor manual was not checked.
7. **Update-check gating copied from the web UI.** The check is made only when the switch has a DNS server (`dns/server`) and its product is not one the UI never checks. Otherwise the plan warns with the reason. A slow or failing check is a warning, never a plan failure.
8. **The upgrade is `foundry provider qnap upgrade --env <name> [--yes]`.** It holds the environment lock, checks read-only, asks once and then runs: `check`, `precheck` (`firmware/condition.anomaly` refuses before any write), `install` (`POST firmware/update/live`), `progress` (poll `firmware/status`), `reboot-wait` (unauthenticated `/api/live`), `login` (one new login, never retried) and `verify` (the version equals the offer). There is no second update check before the install; the post-reboot verification against the offered version catches a changed offer. A failure names the step and the version the switch reports, and says a firmware install cannot be rolled back automatically.
9. **Unverified against a real switch.** Only read calls were verified on a live switch. `firmware/update/check` timed out in the probe (the cause is unknown), and `POST firmware/update/live` and the `firmware/status` progress values were taken from the UI code only. The install path awaits a maintenance-window run; the documentation says so.

## Rationale

- **`get_plan_notes` instead of a runner:** rejected, see Decision 3.
- **`requests` instead of `http.client`:** `requests` cannot check a pin before the first request byte without a custom adapter. `http.client` through a pinned connection is what GL.iNet uses.
- **Install during `apply`:** rejected. A reboot cuts traffic, and the operator must choose the moment.
- **Version pinning:** rejected. The vendor's latest release is the only target, as for GL.iNet and MikroTik.

## Related Issues

- [#1669](https://github.com/endavis/infrafoundry/issues/1669) QNAP provider with firmware tracking
- [#1670](https://github.com/endavis/infrafoundry/issues/1670) QNAP collector
- [#1671](https://github.com/endavis/infrafoundry/issues/1671) QNAP VLAN and port management
- [#1655](https://github.com/endavis/infrafoundry/issues/1655) GL.iNet firmware upgrade
- [#1665](https://github.com/endavis/infrafoundry/issues/1665) MikroTik RouterOS upgrade

## Related Documentation

- [QNAP provider](../providers/qnap.md)
- [Device config collectors](../guides/device-config-collectors.md)
- [ADR-0005](0005-provider-cli-extensibility.md) provider CLI extensibility
- [ADR-0036](0036-glinet-firmware-is-upgraded-through-the-vendor-online-upgrade-by-a-provider-command.md) GL.iNet firmware upgrade
- [ADR-0037](0037-mikrotik-routeros-is-upgraded-to-the-latest-release-of-a-channel-by-a-provider-command.md) MikroTik RouterOS upgrade
