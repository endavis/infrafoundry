---
title: "QNAP Provider"
description: "Track the firmware of a QNAP QSW-M series switch over its web JSON API, with a pinned certificate and a provider upgrade command"
audience:
  - users
tags:
  - providers
---

# QNAP Provider

The QNAP provider manages one QNAP QSW-M series switch per environment over the JSON API of its web UI. For now it tracks the switch's firmware: `infra plan` reports whether the vendor offers a newer release, and `foundry provider qnap upgrade` installs it. It does not generate Terraform. The decision and the rejected alternatives are in [ADR-0038](../decisions/0038-qnap-switches-are-managed-over-the-web-uis-json-api-with-firmware-upgraded-by-a-provider-command.md).

The API is not documented by the vendor. It was read from the web UI's JavaScript and from read-only probes, so the provider treats every reply defensively and reports a changed shape as an error that names the endpoint. See [Verification status](#verification-status).

## Settings

```yaml
provider_settings:
  qnap:
    api_url: https://192.0.2.10
    username: secret://env_secrets/qnap/username
    password: secret://env_secrets/qnap/password
    tls_fingerprint: "AB:CD:EF:..."   # SHA-256 of the switch's certificate
    # verify_ssl: false               # unsafe: skips the pin
    # timeout: 10
    # check_timeout: 90
    # upgrade_timeout: 1200
```

| Key | Meaning |
| :-- | :-- |
| `api_url` | `https://` base URL of the switch (port 443 unless given). |
| `username`, `password` | Must be `secret://` references; a plaintext value is rejected. |
| `tls_fingerprint` | SHA-256 of the switch's certificate, with or without `:` separators. |
| `verify_ssl` | `false` skips the certificate pin and logs a warning on every connection. Without `tls_fingerprint` it is required. |
| `timeout` | Seconds for every request. Default 10, range 1-120. |
| `check_timeout` | Seconds for the vendor update check only. Default 90, range 10-600. |
| `upgrade_timeout` | Seconds from the install request until the switch is back. Default 1200, range 300-3600. |

Read the fingerprint with:

```bash
openssl s_client -connect 192.0.2.10:443 </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256
```

The pin is checked during the TLS handshake, before any request byte is sent. After a reset or a certificate change the pin no longer matches and the provider says so; re-pin `tls_fingerprint`.

## Supported Resources

| Type | Purpose |
| :-- | :-- |
| `firmware.update` | Marks the switch whose firmware follows the vendor's latest release. No fields; at most one per environment; no version pinning. |

```yaml
# envs/lab/resources/switch-firmware.yaml
resources:
  - name: sw-firmware
    provider: qnap
    type: firmware.update
```

The resource is never applied. Apply succeeds with no changes; the install is a separate command because it reboots the switch.

## Plan output

`infra plan` prints one line per run and never fails because of it:

```text
qnap_rest: firmware.update 'sw-firmware': 2.5.0 → 2.6.0 available (run foundry provider qnap upgrade --env lab)
qnap_rest: firmware.update 'sw-firmware': up to date (2.5.0)
qnap_rest: firmware.update 'sw-firmware': update check skipped: the switch has no DNS server; ...
qnap_rest: firmware.update 'sw-firmware': update check failed: the switch did not answer '/api/v1/firmware/update/check' in time
```

The line is skipped on targeted plans that exclude the resource and on drift runs, so scheduled runs never ask the vendor. Because the check is slow, `infra plan` can block for up to `check_timeout` seconds.

## What the switch needs for the update check

The switch asks the vendor's update server itself. It needs a DNS server configured and a route to that server. The provider copies the web UI's rule: it checks only when `dns/server` holds a non-empty address, and skips the check, with a warning, for a product whose web UI never checks. A slow or failed check is a warning, not an error.

## The upgrade command

```bash
foundry provider qnap upgrade --env lab
foundry provider qnap upgrade --env lab --yes
```

There is no `--device`: one switch per environment. The command holds the environment lock, checks read-only, asks once (unless `--yes`), installs and re-plans. The steps are:

1. **check**: read the installed firmware and the vendor's offer. A skipped or failed check stops the command with the reason.
2. **precheck**: refuse before any write when `firmware/condition` reports an anomaly.
3. **install**: renew the session token, then `POST firmware/update/live`.
4. **progress**: poll `firmware/status` every 5 seconds until `done`. `failed` stops with the switch's message. A lost connection means the switch went down. `none` for 60 seconds after the request means the install did not start.
5. **reboot-wait**: poll the unauthenticated `/api/live` until the switch is unreachable, then until it answers.
6. **login**: one new login after the reboot.
7. **verify**: the installed version must equal the offered one.

There is no second update check before the install: the install acts on the check made moments earlier in the same session, and the verification against the offered version catches a changed offer. A failure names the step and the version the switch reports, and says that a firmware install cannot be rolled back automatically.

!!! warning "Run it from a path that does not cross the switch"
    Run the command from a machine that reaches the management address directly, not over a path through the switch's own uplink, or the polling loses its connection for the whole outage.

!!! warning "Plan the outage"
    The reboot interrupts traffic through the switch. On a core or uplink switch that cuts everything behind it for the duration. Run the command when the outage is acceptable.

## Login and lockout

A login is one `POST users/login`. A refusal is never retried, because the switch's lockout behaviour is unknown: the web UI's code shows only "Invalid username or password." and no lockout message, and the vendor manual was not checked. The password is sent in the UI's encoding (base64 of the UTF-16 code units masked to 8 bits). It, the encoded form and the session token never reach a log line, an error message or a `repr`.

## Verification status

- **Verified on a switch (read-only):** login and logout, token renewal, `firmware/info`, `firmware/condition`, `dns/server`, `/api/about`, `/api/live`.
- **Unverified:** `firmware/update/check` (it timed out in the probe; the cause is unknown), `POST firmware/update/live` and the `firmware/status` progress values during an install. They come from the web UI's code. The install path awaits a run in a maintenance window; treat the first upgrade as a test.
- **Out of scope:** the UI's offline upload paths (`firmware/update/local` and chunked upload).

## Doctor

`foundry infra doctor --env <env> -P qnap` checks the settings offline (secret references, pin, ranges, resource schema) and then, online, that the switch answers, the pin matches and a login works. It reports the installed firmware and warns when `verify_ssl` is false.

## Limitations

- One switch per environment.
- No VLAN or port management yet (#1671) and no collector (#1670).
