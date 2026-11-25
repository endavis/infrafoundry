---
title: "ADR-0036: GL.iNet firmware is upgraded through the vendor online upgrade by a provider command"
description: A glinet.firmware resource is upgraded by foundry provider openwrt upgrade through the vendor online upgrade, with a pinned certificate and no login retry
date: 2026-11-24
audience:
  - contributors
tags:
  - adr
---

# ADR-0036: GL.iNet firmware is upgraded through the vendor online upgrade by a provider command

## Status
Accepted

## Context
Issue #1655 asks that a GL.iNet router's firmware can be kept at the vendor's latest release. The OpenWrt provider (ADR-0028) manages a device over SSH with a key and stores no password; several devices per environment are provider instances (ADR-0035). The vendor's own upgrade runs through the router's web JSON-RPC API, which needs the admin password and serves a self-signed certificate. The router locks the account after repeated failed logins, and a flash cannot be rolled back automatically.

## Decision
A `glinet.firmware` resource marks a device whose firmware follows the vendor's latest release. It has no fields, at most one per device.

- **Vendor online upgrade over JSON-RPC, not sysupgrade.** The command calls `check_firmware_online`, then `upgrade_online {keep_config: true, keep_package: true}`, polls `get_online_upgrade_status` and waits for the router to come back. The flow follows the router's own web UI.
- **Trigger is a provider command (ADR-0005).** `foundry provider openwrt upgrade --env <env> [--device <name>] [--yes] [--lock-timeout N]` holds the environment lock, checks every selected device read-only, prompts once, upgrades one device at a time and re-plans the upgraded provider ids. `infra plan` only reports "up to date" or "current to new available"; `infra apply` never upgrades. A firmware-only device skips the ansible pass.
- **A firmware check failure in a plan is a warning**, not an error, so a router with its web UI down cannot block SSH configuration management. The upgrade command fails hard. Drift runs (`add_only`) never log in to the router.
- **The admin password is a `secret://` setting** (`web_password`), a shared default that a device entry may override. This reverses ADR-0028's "the provider stores no password" for this resource only. The password, the crypt cipher, the login hash and the session id never reach a log, an error or a `repr`.
- **The certificate is pinned.** `tls_fingerprint` (SHA-256 of the router's certificate, hex with or without colons) is checked during the TLS handshake, before any request byte is written. `verify_ssl: false` is the only way to skip it, is documented as unsafe, logs a warning on every connection, and, like the pin, is per-device only so the opt-out names the router it applies to. Neither key set is a validation error.
- **A failed login is never retried.** One `challenge` and one `login` per session, because the device locks out.
- **The first device failure stops the run.** A failure points at API drift, a bad vendor release or a network problem that would probably repeat on the next router. The error lists upgraded, failed and not-attempted devices.
- **`--device` exists on this command only.** ADR-0035 left it off the four `infra` commands; this command is per-device by nature.
- **Pure-Python crypt.** The login challenge names MD5-crypt, SHA-256-crypt or SHA-512-crypt. The standard library's `crypt` is gone in Python 3.13 and no declared dependency provides them, so they are implemented from the published algorithms rather than adding a dependency. An unknown algorithm raises before `login` is sent, so it costs no login attempt.
- **`Orchestrator.environment_lock`** is a new public context manager over the existing lock, so a command outside apply and destroy can exclude them.

### Choices not fixed by the issue

- **`empty_result` also covers destroy.** The provider skips the ansible pass whenever a run has no items, no forgotten rows and no forgotten items, in apply and in destroy mode, so a firmware-only device never needs SSH for either.
- **The login hash method comes from the challenge.** The hash is `sha256(user:cipher:nonce)` unless the challenge carries a `hash-method` of `md5`, `sha256` or `sha512`, which is then used. An unknown value raises before `login`.
- **Unverified against a real router:** the `hash-method` challenge field (added as a guard; no router has been seen sending it) and the shape of the `logout` request (`{"method": "logout", "params": {"sid": ...}}`; its errors are ignored). The offered shape of `check_firmware_online` (`version_new`) was read from the web UI's JavaScript, and a live offered reply has not been captured. Treat all three as unverified until a router run confirms them.

## Rationale
The vendor flow is what the router's own UI uses, so it verifies the image and signature itself and keeps the configuration. A provider command keeps a flash, which is slow and cannot be undone, out of `apply`, where a routine run could trigger it. Pinning the certificate gives integrity without a trusted CA, and avoiding `verify=False` keeps the check explicit and auditable.

Alternatives rejected:

- **`sysupgrade` over SSH with a downloaded image.** It needs the controller to choose and verify images per model.
- **Upgrading from `infra apply`.** A flash would hide inside a routine apply.
- **Retrying a failed login.** The device locks out.
- **A new dependency for crypt.** Three short algorithms with published vectors do not justify one.

## Related Issues

- Issue #1655: keep GL.iNet firmware at the vendor's latest release
- Issue #1656: several OpenWrt devices per environment (ADR-0035)

## Related Documentation

- [OpenWrt provider: GL.iNet firmware](../providers/openwrt.md#glinet-firmware)
- [ADR-0005: Provider CLI extensibility](0005-provider-cli-extensibility.md)
- [ADR-0028: OpenWrt devices are managed through generated playbooks](0028-openwrt-devices-are-managed-through-generated-communityopenwrt-playbooks-with-ubus-apply-rollback.md)
- [ADR-0035: OpenWrt devices are provider instances](0035-openwrt-devices-are-provider-instances-several-per-environment.md)
- [ADR-0037: MikroTik RouterOS is upgraded to the latest release of a channel by a provider command](0037-mikrotik-routeros-is-upgraded-to-the-latest-release-of-a-channel-by-a-provider-command.md)
