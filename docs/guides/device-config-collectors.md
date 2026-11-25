---
title: "Device Config Collectors"
description: "Back up the configuration of unmanaged network devices into the config repo with read-only collectors"
audience:
  - users
tags:
  - guides
---

# Device Config Collectors

## Overview

Some devices are never managed by InfraFoundry: an ISP-supplied ONT or router, or a travel
router. `foundry infra collect` reads their configuration and stores it in the config repo, so
a change on the device shows up in git. Collectors are **read-only**: they never write to a
device, plan nothing, keep no state database rows and generate no Terraform. See
[ADR-0027](../decisions/0027-unmanaged-network-devices-are-backed-up-by-read-only-collectors.md).

```bash
foundry infra collect --env home               # every device in the environment
foundry infra collect --env home -d ont-isp    # one device (repeatable)
```

The command prints `new:` or `changed:` for each file that differs from the last run, and
`No changes.` when nothing did. A failing device does not stop the others; the command exits
non-zero after the summary.

## Configuration

Add a `collectors:` section to `envs/<env>/settings.yaml`:

```yaml
collectors:
  output_dir: device-configs/home   # optional; default device-configs/<env>
  devices:
    - name: ont-isp
      type: huawei-ont-web
      address: http://192.0.2.1
      username: secret://env_secrets/ont-isp/username
      password: secret://env_secrets/ont-isp/password
    - name: switch-core
      type: routeros-rest
      address: http://192.0.2.2
      username: secret://env_secrets/switch-core/username
      password: secret://env_secrets/switch-core/password
    - name: switch-core-qnap
      type: qnap-qsw-rest
      address: https://192.0.2.3
      username: secret://env_secrets/switch-core-qnap/username
      password: secret://env_secrets/switch-core-qnap/password
      options:
        tls_fingerprint: "AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89"
    - name: travel-router
      type: openwrt-ssh
      address: 198.51.100.7
      username: root
      ssh_key_file: ~/.ssh/id_ed25519
```

Device names are kebab-case. Optional fields: `port`, `verify_ssl` (default `true`),
`timeout` (default 30 seconds) and `options`. `output_dir` is relative to the config repo
root, must stay inside it and must not be under `envs/`, where it would be discovered as a
provider.

With a `secret_backends.bitwarden` block in `settings.yaml`, `secret://bitwarden/<item>/<field>` works wherever `secret://env_secrets/...` does. See [Bitwarden / Vaultwarden secret backend](../configuration/secrets-vaultwarden.md).

## Output

```text
device-configs/<env>/<device>/
  config.xml.sops.json     # secret-bearing, SOPS-encrypted
  ip-route.txt             # plaintext
```

Secret-bearing exports are encrypted whole-file with SOPS (binary input, JSON output). The
plaintext only ever exists in a temporary directory that is removed afterwards. Add a creation
rule to the config repo's `.sops.yaml`:

```yaml
creation_rules:
  - path_regex: device-configs/.*\.sops\.json$
    age: <your age public key>
```

Without a matching rule the run fails with `no .sops.yaml creation rule matches <path>`.

## Change detection

The previous encrypted file is decrypted in memory and its SHA-256 compared with the new
plaintext. An unchanged artifact is not rewritten, so re-encryption causes no churn in git. If
the previous file cannot be decrypted it is reported as `changed (previous unreadable)` and
replaced. Volatile output is normalised first: the RouterOS export timestamp line and the
`valid_lft`/`preferred_lft` lines of `ip addr`.

The Huawei ONT export stores its secrets as `$2...$` values and re-salts them on every
download, and its LAN host table carries runtime attributes (`LastStatusChangeTime`,
`IsOnlineFlag`), so two exports of an unchanged device always differ. For that collector the
comparison masks those values (the stored file keeps them). A change to only such a value,
for example a new Wi-Fi key and nothing else, is therefore not reported.

The QNAP native export, `system-config.bin`, is off by default. When enabled with
`options.native_export: true` it is compared byte for byte, and because the export is not
byte-stable it is reported as changed on every run.

## Collectors

### huawei-ont-web

Huawei ONT web UI (HG8xxx family). Downloads the plain config export, `config.xml`
(always encrypted). Options: `language` (default `english`) and `config_page` (default
`html/ssmp/cfgfile/cfgfileptvdf.asp`).

!!! warning "Lock-out caveat"
    These units lock the login after a few failed attempts and allow one session. The
    collector makes exactly **one** login attempt per run, never retries, and always logs out.
    Close any browser session on the device first. If the login fails, fix the credentials
    before running again.

### routeros-rest

MikroTik RouterOS over REST, for devices not managed by the [MikroTik provider](../providers/mikrotik.md).
Runs `/export terse` and stores `export.rsc` (always encrypted). Plain `http://` URLs are
accepted.

### qnap-qsw-rest

QNAP QSW-M series switches over the web UI's JSON API, reusing the client of the
[QNAP provider](../providers/qnap.md). One login per run, never retried, and the session is
always logged out. The address must be `https://`. Pin the switch's certificate with
`options.tls_fingerprint` (SHA-256), or, unsafely, set `verify_ssl: false`.

The collector reads the configuration endpoints only (system, firmware, VLANs, ports, link
aggregation, spanning tree, LLDP, QoS, ACLs, IGMP, mirroring, DNS, IP interfaces and routes,
time, web and HTTPS settings, syslog, SNMP and users) and stores one JSON document per endpoint,
for example `vlan.json` and `ip-ipv4-route.json`. Status and statistics endpoints are left out.
Documents with credentials or the switch MAC address (`system-info.json`, `users.json`,
`snmp-community.json`, `snmp-security.json`) are encrypted; the others are plaintext so git
diffs stay readable.

The switch's native export is off by default. Set `options.native_export: true` to store it as
`system-config.bin` (encrypted). It is opaque and can be restored through the switch's web UI,
but it is not byte-stable, so it is reported as changed on every run.

Endpoints a firmware does not serve are listed with a reason in `unavailable.json` and do not
fail the run. A file kept from an earlier run for an endpoint that is now unavailable is not
deleted; check `unavailable.json`. The run fails if `system/info`, `firmware/info` or `vlan`
is unavailable, so an API change never writes an empty backup.

### openwrt-ssh

OpenWrt and GL.iNet routers over SSH, with **key authentication only** (`ssh -o BatchMode=yes`).
Host-key checking stays on, so add the host key first (`ssh-keyscan` or a first manual login).
Collects `uci export` for `network`, `dhcp`, `firewall` and `wireless` (skipped when the device
has no wireless package), `ip addr`, `ip route` and the model and firmware version. The UCI
files are redacted (`key`, `password`, `sae_password`, `psk`, `private_key`, `preshared_key`,
`auth_secret`, `acct_secret`, `priv_key_pwd`) and also encrypted. The other files are plaintext.

To manage an OpenWrt device rather than back it up, use the [OpenWrt provider](../providers/openwrt.md).

## Logging

Collectors log only device names, artifact names and statuses. Credentials, tokens and
exported content are never logged.
