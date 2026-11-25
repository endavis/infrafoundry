---
title: "QNAP Provider"
description: "Manage the VLANs, LACP groups and port settings of a QNAP QSW-M series switch and track its firmware over its web JSON API, with a pinned certificate, lock-out checks and a provider upgrade command"
audience:
  - users
tags:
  - providers
---

# QNAP Provider

The QNAP provider manages one QNAP QSW-M series switch per environment over the JSON API of its web UI. It manages the switch's VLANs (with their tagged and untagged member ports), LACP groups and port settings, and it tracks the firmware: `infra plan` reports whether the vendor offers a newer release, and `foundry provider qnap upgrade` installs it. It does not generate Terraform. The decisions and the rejected alternatives are in [ADR-0038](../decisions/0038-qnap-switches-are-managed-over-the-web-uis-json-api-with-firmware-upgraded-by-a-provider-command.md) (provider and firmware) and [ADR-0039](../decisions/0039-qnap-switch-vlans-and-lacp-groups-are-managed-by-the-direct-runner-with-a-full-list-membership-model-and-fail-closed-lock-out-checks.md) (VLANs, LACP groups, port settings and the lock-out checks).

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
    # management_vlan: 1              # the VLAN the management address lives on
    # protected_ports: [1, lag1]      # ports that carry your management traffic
    # allow_lockout_risk: false       # unsafe: turn lock-out refusals into warnings
    # liveness_timeout: 60
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
| `management_vlan` | The VLAN the management address lives on, 1-4094. Without it the provider infers it from the switch's IP interface (see [The lock-out hazard](#the-lock-out-hazard)). |
| `protected_ports` | Ports that carry your management traffic: integers, or `lagN` for LACP group `N`. The API cannot tell which ports these are, so you say. |
| `allow_lockout_risk` | `true` turns the lock-out refusals about the management VLAN and protected ports into warnings. Default `false`. Doctor warns while it is set. |
| `liveness_timeout` | Seconds apply waits for the switch to answer after its writes. Default 60, range 10-600. |

Read the fingerprint with:

```bash
openssl s_client -connect 192.0.2.10:443 </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256
```

The pin is checked during the TLS handshake, before any request byte is sent. After a reset or a certificate change the pin no longer matches and the provider says so; re-pin `tls_fingerprint`.

## Supported Resources

| Type | Purpose |
| :-- | :-- |
| `vlan` | A VLAN and its member ports. Key `id` (1-4000); fields `tagged`, `untagged` (lists of ports) and `absent`. |
| `lacp.group` | A link aggregation group. Key `group`; fields `mode` (the switch's `AggrMode`, verbatim), `members` (physical ports) and `absent`. |
| `port` | The settings of one physical port. Key `port` (a number); fields `alias`, `shutdown`, `speed`, `duplex`, `flow_control`, `fec` and `mtu`. Never created or deleted. See [Port settings](#port-settings). |
| `firmware.update` | Marks the switch whose firmware follows the vendor's latest release. No fields; at most one per environment; no version pinning. |

A port is an integer (a physical port) or `lagN`, the interface of LACP group `N`. The provider maps `lagN` to interface number `N + StartIndex`, where `StartIndex` is `lacp/info.StartIndex`; this numbering comes from the web UI's code and is unverified on a device.

```yaml
# envs/lab/resources/switch-vlans.yaml
resources:
  - name: uplink
    provider: qnap
    type: lacp.group
    config:
      group: 1
      mode: lacp
      members: [7, 8]

  - name: servers
    provider: qnap
    type: vlan
    config:
      id: 10
      tagged: [lag1]
      untagged: [1, 2, 3]

  - name: guests
    provider: qnap
    type: vlan
    config:
      id: 20
      tagged: [lag1]
      untagged: [4]
```

In a `resources/` file the fields go under `config:`; fields placed directly on the entry are not read.

```yaml
# envs/lab/resources/switch-ports.yaml
resources:
  - name: spare-port-5
    provider: qnap
    type: port
    config:
      port: 5
      alias: spare-5
      shutdown: false
      speed: auto
      flow_control: false
```

```yaml
# envs/lab/resources/switch-firmware.yaml
resources:
  - name: sw-firmware
    provider: qnap
    type: firmware.update
```

The `firmware.update` resource is never applied. Apply succeeds with no changes for it; the install is a separate command because it reboots the switch.

The switch has no VLAN name, so the YAML resource name is only a label and is never written. It also has no separate PVID: a port's untagged VLAN is its PVID.

## Membership semantics

A VLAN declares its own member lists, and every write to the switch carries the complete list of that VLAN.

- **A declared list replaces.** When `tagged` is declared, the VLAN's tagged ports become exactly that set; tagged ports not in it are removed. The same holds for `untagged`.
- **An omitted list is kept.** A field you leave out keeps its live value. A port that `tagged` names and that is live-untagged moves to tagged when `untagged` is omitted, and the other way round.
- **A port is untagged in at most one VLAN.** When a port becomes untagged in VLAN X, the provider removes it from every other VLAN that holds it untagged, VLANs you do not declare included. The plan says so, for example `vlan 30 (unmanaged): untag port 5 (moves to vlan 10)`.
- **Losing the last untagged VLAN warns.** A port that ends untagged in no VLAN produces `port N will have no untagged VLAN`.
- **VLANs and ports you do not declare are untouched**, apart from that untag strip.
- **VLAN 1** can be declared to manage its membership. It is never created or deleted, and `absent: true` on it is a schema error.

## Port settings

A `port` resource sets fields of one physical port. It is a settings resource: the port always exists, so the provider never creates or deletes it, and `absent` is a schema error.

| Field | Values | Notes |
| :-- | :-- | :-- |
| `port` | an integer of 1 or more | The key. `lagN` is a schema error, and so is a port that is not on the switch or is a LACP interface row (a plan error). |
| `alias` | a string | The port's label on the switch. |
| `shutdown` | `true` / `false` | `true` administratively disables the port. |
| `speed` | `auto`, `10M`, `100M`, `1G`, `2.5G`, `5G`, `10G` | `auto` negotiates; the others fix the speed. |
| `duplex` | `full`, `half` | Needs a fixed `speed`. `half` is allowed only at `10M` or `100M`. Undeclared: a change between fixed speeds keeps the live duplex, a change from `auto` writes full duplex. |
| `flow_control` | `true` / `false` | Written as `FC`. |
| `fec` | `auto`, `rs`, `fc`, `none` | Only on a port that has FEC; on any other port the plan fails. The plan also fails when it would leave fewer than two ports with FEC on a switch that has FEC ports (the web UI's rule). |
| `mtu` | a positive integer | The MTU looks switch-wide, so every `port` that declares `mtu` must declare the same value. |

Only declared fields are compared and written; undeclared fields and undeclared ports keep their live values and are not listed as unmanaged. `speed: auto` is compared against the port's auto-negotiation flag, never against the negotiated speed it currently shows.

Each changed port is one `PUT portlist` with the 60 s timeout the web UI uses. The body is an array, `[{"idx": "<port>", "data": {...}}]`, and `data` is the port's whole live row with the declared fields edited, as the web UI sends it. Plan lines name the changed fields, never their values: `port 5: set alias, speed`.

A `port` row that leaves the YAML is released from the managed set and the port keeps its settings. `infra destroy` never writes `portlist`.

## Existing Objects, Deletes and Unmanaged Objects

A declared VLAN or LACP group that already exists is compared field by field and updated only when it differs. Objects that exist on the switch but are not declared are listed in the plan as `unmanaged (kept)`.

Deletes follow [ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md): the provider deletes an undeclared object only when InfraFoundry applied it earlier and its YAML has since gone, or when you declare it with `absent: true` (key fields only). Add-only runs, which means drift detection and any run with `--target`, never delete: an `absent: true` entry is shown as `skipped: add-only`.

## The lock-out hazard

A wrong VLAN or LACP change can cut the connection you manage the switch over, and the API cannot tell which ports carry that connection. The provider therefore refuses an end state that could cut it (fail closed) and prints the refusal instead of writing.

**Management VLAN.** `management_vlan` wins when set. Otherwise the provider infers it from `ip/ipv4/interface`, only when exactly one interface is enabled and its key is a VLAN id; that is an inference and the plan warns `inferred ... unverified; set management_vlan to confirm`. When it cannot be determined and the plan has a write, the plan is refused.

**Refusals.** The plan is refused when its end state would:

1. delete the management VLAN;
2. with `protected_ports` set, drop a protected port from the management VLAN or flip its Tagged flag (checked for ports that are live members);
3. without `protected_ports`, remove any live member of the management VLAN or flip its Tagged flag;
4. put a protected physical port into a LACP group;
5. delete a LACP group whose interface is protected, or remove members from it;
6. shut down a watched port;
7. change the `speed`, `duplex` or `fec` of a watched port;
8. change the `mtu` of any port, because the MTU looks switch-wide (unverified);
9. delete a LACP group that a remaining VLAN still lists. This one is never overridable.

The *watched* ports for refusals 6 and 7 are `protected_ports` (a `lagN` entry stands for the group's member ports) or, without `protected_ports`, the members of the management VLAN, including the members of any LACP group it lists. `alias`, `flow_control` and enabling a port are never a risk. Adding members to the management VLAN is always allowed. A protected port that is not a member of the management VLAN only warns.

**Override.** `allow_lockout_risk: true` turns refusals 1 to 8 into warnings. Every plan prints a warning while it is set and `infra doctor` warns too. Use it only when you can reach the switch another way.

**Write order.** The writes run in nine phases:

| Phase | What runs | Why |
| :-- | :-- | :-- |
| A | `lacp.group` creates | A LAG interface must exist before a VLAN lists it. |
| B | Remove an untagged port from the VLAN that gives it away | Lets a port move, and two VLANs swap ports. |
| C | `vlan` creates | |
| D | `vlan` updates, the management VLAN last | |
| E | `lacp.group` updates | Ports joining or leaving a LAG take the membership set in D. |
| F | `vlan` deletes | |
| G | `lacp.group` deletes | |
| H | `port` updates, watched ports last | Port settings come after the VLANs and LACP groups they depend on. |
| I | `port` updates that include `mtu`, watched ports last | A port whose change includes `mtu` is written here with all of its changes. |

**After the writes** the provider polls the switch's unauthenticated `/api/live` until `liveness_timeout` runs out, then logs in again and reads `vlan` and `lacp/group` back, and `ports` too when a port step completed. If the switch does not answer, the apply fails, names the steps that completed and says the switch stopped answering. If the read-back differs from the plan for an object that was written, the apply fails and names the object. A port is compared on its declared fields only, with the same rules as the plan. After an `mtu` write, the apply warns when undeclared physical ports now show the new MTU too, which confirms the MTU is switch-wide.

!!! tip "Before the first apply"
    Run `foundry infra collect --env <env>` first: the [`qnap-qsw-rest` collector](../guides/device-config-collectors.md#qnap-qsw-rest) stores the VLAN and LACP configuration and is your restore point. Apply from a machine whose path to the switch does not cross the ports you change, and keep physical access in mind.

## Apply and Destroy

`infra apply` plans against the switch, then runs the steps in order and stops at the first error. A failure names the step, the switch's error code and the steps that already ran. `infra destroy` deletes the VLANs and LACP groups you declare that exist on the switch, with the same lock-out checks on the end state; it never deletes VLAN 1, `absent: true` entries or undeclared objects.

## Drift Detection

`infra drift detect` runs the plan add-only: it reports declared objects that are missing or differ and never deletes. A firmware-only environment reports no drift.

## Plan output

`infra plan` prints a summary per type (`vlan: 1 to create, 2 to update, 0 to delete, 3 unmanaged (kept)`), one line per untag move, the phases and any warnings. A refused plan fails with the reasons. For the firmware it prints one line per run and never fails because of it:

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
- **Verified on a switch (write):** `POST vlan` creating an unused VLAN with no members, and `DELETE vlan` removing it. `DELETE vlan` takes `{"idx": ["<id>"]}`, a list of string keys; a scalar id is refused with 400. A VLAN with no members reads back as `"val": null`, which the provider reads as no members.
- **Unverified:** `PUT vlan` (changing members), every `lacp/group` write, and the numbering of LAG interfaces. They come from the web UI's code. The post-apply read-back checks each write on the first use.
- **Verified on a switch (port write):** `PUT portlist` with the array body described under [Port settings](#port-settings), changing the `alias` of a port in auto mode and then changing it back. The switch accepted the body, the read-back passed, a second plan was clean, and no other field of the port changed.
- **Unverified port writes:** `shutdown`, `speed` and `duplex`, `flow_control` and `fec` are fields the web UI itself edits, but none was changed on a device. `mtu` is never edited by the UI, so whether the switch accepts a changed value, and whether it applies to every port, is unknown until the first apply. The read-back reports an ignored write by naming the port. The `GET ports` shape was read on a real switch (read-only), including the LACP interface rows with `Type` `ieee8023ad`.
- **Out of scope:** the UI's offline upload paths (`firmware/update/local` and chunked upload).

## Doctor

`foundry infra doctor --env <env> -P qnap` checks the settings offline (secret references, pin, ranges, the `vlan`, `lacp.group` and `port` schema) and then, online, that the switch answers, the pin matches and a login works. It reports the installed firmware and warns when `verify_ssl` or `allow_lockout_risk` is set.

## Limitations

- One switch per environment.
- A `port` can only be a physical port. LACP interface rows (`lagN`) are not managed, because the web UI's handling of them was not traced.
- The MTU is treated as switch-wide, and a change is refused unless `allow_lockout_risk` is set, until a live check shows otherwise.
- Port settings that the web UI does not offer (such as storm control or PoE) are not managed.
- The configuration backup is the [`qnap-qsw-rest` collector](../guides/device-config-collectors.md#qnap-qsw-rest).
