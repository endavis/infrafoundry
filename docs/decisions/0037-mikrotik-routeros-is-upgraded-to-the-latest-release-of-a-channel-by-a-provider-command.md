---
title: "ADR-0037: MikroTik RouterOS is upgraded to the latest release of a channel by a provider command"
description: A system.package.update resource is upgraded by foundry provider mikrotik upgrade in two rebooting stages, never by apply, with success proven by polling
date: 2026-11-25
audience:
  - contributors
tags:
  - adr
---

# ADR-0037: MikroTik RouterOS is upgraded to the latest release of a channel by a provider command

## Status
Accepted

## Context
Issue #1665 asks that a MikroTik RouterOS device can be kept at the latest release of an update channel, as ADR-0036 does for GL.iNet firmware. The MikroTik provider (ADR-0026) manages one device per environment over the REST API. RouterOS updates in two stages that each end in a reboot: the packages (`system/package/update`), then the RouterBOARD firmware (bootloader, `system/routerboard`), which lags the packages on real hardware. A device used as a WAN-edge switch cuts traffic for everything behind it during each reboot, and an installed package or flashed firmware cannot be rolled back automatically.

## Decision
A `system.package.update` resource marks the device whose RouterOS follows the latest release of a channel. Its only field is `channel` (`stable` by default, `long-term`, `testing`, `development`); at most one per environment; a pinned version is rejected.

- **Name.** The provider's convention is that a type with `.` turned into `/` is its REST path and YAML fields use RouterOS names. `/rest/system/package/update` holds `channel`, `installed-version` and `latest-version`. `system.firmware` was rejected because OPNsense's type of that name upgrades during `apply`.
- **Trigger is a provider command (ADR-0005).** `foundry provider mikrotik upgrade --env <env> [--yes] [--lock-timeout N]` holds the environment lock, checks read-only, prompts once, runs the stages and re-plans. `infra apply` and `infra destroy` never upgrade or reboot: the type is not in the manager's `SPECS`, so they get no diff and no step. There is no `--device`: MikroTik has no provider instances.
- **Plan reports only.** `infra plan` prints one line, "up to date", "current to new available" or "RouterBOARD firmware pending", through a duck-typed provider hook called by `MikroTikRestRunner`. A failed check is a warning, never a plan failure. Drift runs (`add_only`) and targeted runs that exclude the resource never ask the vendor.
- **Two stages, two deadlines.** RouterOS first (`install`, wait for the reboot, verify the version), then RouterBOARD when `current-firmware` differs from `upgrade-firmware` (`routerboard/upgrade`, `reboot`, wait, verify). Each stage has its own deadline, `provider_settings.mikrotik.upgrade_timeout` (default 900 s, 120 to 3600). A device without RouterBOARD firmware (a CHR, or an API 400 or 404) skips stage 2.
- **Success is proven by polling, not replies.** The write endpoints' replies are unverified, so only their HTTP status is used. The command waits for the device to go down (unreachable, or an `uptime` below the pre-install baseline) and come back, then re-reads the versions. A connection drop on `install` or `reboot` counts as the device going down.
- **The channel switch happens only after the confirmation.** RouterOS checks the channel set on the device. On a mismatch the plan and the command's table make no `check-for-updates` call and write nothing; after confirmation (or `--yes`) the command sets the channel, checks, and upgrades without a second prompt if a release is offered.
- **Failures name the step** (`check`, `install`, `reboot-wait`, `verify-routeros`, `routerboard-upgrade`, `reboot`, `verify-routerboard`) and the versions the device reports, read best effort. `serial-number` is never stored, logged or included in an error.
- **Entry-point registration.** The provider had no `infrafoundry.providers` entry point or `register()`; both are added, with `register_cli`, so the command exists.

### Unverified against a real device

The read-only probe verified `GET system/package/update`, `POST system/package/update/check-for-updates` (a list of progress sections) and `GET system/routerboard`. A live run on a RouterOS 7.25.1 CHR then verified `POST system/package/update/install` (installs and reboots once; the command upgraded the CHR to 7.25.2 and verified it), `POST system/package/update/set` (returns `[]`), the status string `System is already up to date`, and that a CHR answers `GET system/routerboard` with API 400. Still unverified: `POST system/routerboard/upgrade` and `POST system/reboot`, which need RouterBOARD hardware.

## Rationale
A provider command keeps two reboots, which cut traffic and cannot be undone, out of `apply`, where a routine run could trigger them. Polling for down and up and re-reading versions does not depend on the unverified replies, so a different reply shape cannot turn a failed upgrade into a reported success.

Alternatives rejected:

- **Upgrading from `infra apply`.** Reboots would hide inside a routine apply.
- **A `system.firmware` name.** It suggests the OPNsense behaviour of upgrading during apply.
- **A pinned version field.** The goal is to follow a channel; pinning needs a download source and checksums.

## Related Issues

- Issue #1665: keep MikroTik RouterOS at the latest release of a channel
- Issue #1655: keep GL.iNet firmware at the vendor's latest release (ADR-0036)

## Related Documentation

- [MikroTik provider: RouterOS and RouterBOARD updates](../providers/mikrotik.md#routeros-and-routerboard-updates)
- [ADR-0005: Provider CLI extensibility](0005-provider-cli-extensibility.md)
- [ADR-0026: MikroTik RouterOS is managed natively over the REST API by a direct runner](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md)
- [ADR-0036: GL.iNet firmware is upgraded by a provider command](0036-glinet-firmware-is-upgraded-through-the-vendor-online-upgrade-by-a-provider-command.md)
