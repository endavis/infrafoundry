---
title: "MikroTik Provider"
description: "Manage a MikroTik RouterOS 7 device natively over its REST API, with phased changes and a plan-time refusal of lock-outs"
audience:
  - users
tags:
  - providers
---

# MikroTik Provider

The MikroTik provider manages a RouterOS 7 (or later) device over its REST API. It reads the device, diffs it against your YAML, and plans the changes in an order that keeps the management connection alive. It does not generate Terraform: the decision and the rejected alternatives are in [ADR-0026](../decisions/0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md).

!!! note "Verified on a RouterOS CHR"
    `infra plan`, `infra apply`, `infra destroy`, `infra doctor` and `infra drift detect` are implemented. The write calls (PUT, PATCH, DELETE) are covered by unit tests against an in-memory fake device and were verified live against a RouterOS 7.25.1 CHR built with the [`routeros-chr` blueprint](#test-target-a-chr-vm) ([#1483](https://github.com/endavis/infrafoundry/issues/1483)). The live run checked:

    - apply converging, with a clean second plan;
    - enabling `vlan-filtering`;
    - a management move of `ether1` into a filtering bridge without losing the API;
    - drift reported after an out-of-band PVID change;
    - `absent` and managed-set deletes, with unmanaged objects kept;
    - destroy refusing to remove the management path.

    A real switch differs from a CHR in its switch chip and port names, so keep console access for the first apply on new hardware.

## Settings

One device per environment, under `provider_settings.mikrotik` in `envs/<env>/settings.yaml`:

```yaml
providers:
  - mikrotik

provider_settings:
  mikrotik:
    api_url: https://192.0.2.2
    username: secret://env_secrets/mikrotik/username
    password: secret://env_secrets/mikrotik/password
    verify_ssl: true   # default
    timeout: 10        # seconds, default
    upgrade_timeout: 900   # seconds per reboot stage; default 900, range 120-3600
```

`secret://env_secrets/...` references resolve from the environment's SOPS secrets. The password never appears in logs or error messages. With a `secret_backends.bitwarden` block in `settings.yaml`, `secret://bitwarden/<item>/<field>` works wherever `secret://env_secrets/...` does ([Bitwarden / Vaultwarden secret backend](../configuration/secrets-vaultwarden.md)).

`api_url` may use `http`: RouterOS can serve REST on `www` without TLS. Basic-auth credentials then travel in plaintext, so `infra doctor` warns.

## Supported Resources

The resource type with `.` replaced by `/` is the REST path. YAML field names are the RouterOS names.

| Type | REST path | Identity key |
|------|-----------|--------------|
| `interface.bridge` | `/rest/interface/bridge` | `name` |
| `interface.bridge.port` | `/rest/interface/bridge/port` | `interface` |
| `interface.bridge.vlan` | `/rest/interface/bridge/vlan` | `bridge` and the set of `vlan-ids` (ranges such as `10-12` are expanded) |
| `interface.vlan` | `/rest/interface/vlan` | `name` |
| `ip.address` | `/rest/ip/address` | `address` (CIDR); moving it to another interface is an update |
| `ip.dhcp-client` | `/rest/ip/dhcp-client` | `interface` |
| `certificate` | `/rest/certificate` | `name`; created and signed (self-signed), only `comment` changes in place, see [From `www` to HTTPS](#from-www-to-https-and-a-lets-encrypt-certificate) |
| `ip.service` | `/rest/ip/service` | `name`; update only, never created or deleted |
| `system.package.update` | `/rest/system/package/update` | one per environment; never applied, see [RouterOS and RouterBOARD Updates](#routeros-and-routerboard-updates) |

For types keyed by `name`, the resource name is the default. Declare the objects in the resource-centric format, with the type in each entry (the provider-centric file name cannot carry the hyphen of `ip.dhcp-client`):

```yaml
# envs/lab/resources/switch.yaml
resources:
  - name: bridge
    provider: mikrotik
    type: interface.bridge
    config:
      vlan-filtering: true

  - name: uplink
    provider: mikrotik
    type: interface.bridge.port
    config:
      interface: ether1
      bridge: bridge
      pvid: 99

  - name: mgmt-vlan
    provider: mikrotik
    type: interface.bridge.vlan
    config:
      bridge: bridge
      vlan-ids: 99          # or "10,20-22"
      tagged: [bridge, ether4]
      untagged: [ether1]

  - name: vlan99
    provider: mikrotik
    type: interface.vlan
    config:
      interface: bridge
      vlan-id: 99

  - name: mgmt
    provider: mikrotik
    type: ip.address
    config:
      address: 192.0.2.2/24
      interface: vlan99

  - name: factory
    provider: mikrotik
    type: ip.address
    config:
      address: 192.168.88.1/24   # the RouterOS factory default
      absent: true

  - name: www-ssl
    provider: mikrotik
    type: ip.service
    config:
      port: 443
      disabled: false
```

## Existing Objects, Deletes and Unmanaged Objects

Objects are matched by their identity key, so a device that is already configured (default bridge, factory address, built-in services) is adopted with no import step. Only the fields your YAML sets are compared, after normalizing RouterOS's string values (`"true"`, `"yes"`, `"10"`), so a converged device plans clean. Dynamic rows (DHCP-assigned addresses, dynamic bridge VLAN entries) are ignored.

- `absent: true` on an entry deletes the matching live object. It is the way to remove the factory `192.168.88.1/24`. An absent entry carries only its key fields.
- An object InfraFoundry applied before and that your YAML no longer declares is deleted ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)).
- Any other live object is reported as `unmanaged (kept)` and left alone.
- A filtered run (`-r`, `-p`) is add-only.

## The Lock-Out Hazard

A bridge with `vlan-filtering` on drops traffic it has no VLAN entry for. The REST API has no safe mode, so a wrong order or a wrong end state cuts the connection that applies the change. The plan therefore does two things.

**It orders the changes in phases:**

| Phase | What runs |
|-------|-----------|
| A | Disable `vlan-filtering` on bridges going from on to off |
| B | Creates in dependency order; signing of created or unsigned certificates (right after the create); bridge VLAN membership widened to old and new; port PVID updates on bridges whose filtering is off at that moment |
| C | Enable `vlan-filtering` on bridges going from off to on |
| D | Narrowing: exact bridge VLAN membership, PVID updates on filtering bridges, other updates |
| E | Deletes in reverse dependency order |
| F | `ip.service` updates |

Changes that touch the live management path sort last within D and E. The plan prints the number of steps per phase.

**It refuses an unsafe end state.** The management address is the host of `api_url` (a hostname is resolved once). The plan fails, and says why, when the end state would leave:

- no address on the device that contains the management address;
- a management address held by a DHCP lease whose `ip.dhcp-client` the plan removes or disables (the interface that holds the lease gets the same path checks as a static address);
- the management interface as a bridge port;
- a management VLAN interface whose bridge filters, but whose bridge VLAN entry does not hold the bridge in `tagged`, or has no member port (tagged, untagged, or `pvid` equal to the VLAN);
- a management bridge that filters with no port whose `pvid` matches the bridge's;
- the `ip.service` the provider connects through (`www` for http, `www-ssl` for https) disabled, or moved off the `api_url` port. A change to its `address` list only warns.

- an `ip.service` naming a `certificate` that will not exist signed after the plan;
- a `certificate` deleted while a live `ip.service` still uses it (switch the service in an earlier apply);
- `www-ssl` moved to a certificate the plan creates while `api_url` is `https` with `verify_ssl` on (a self-signed certificate cannot validate).

If the host cannot be resolved and the plan touches bridge, VLAN or address types, the plan refuses.

!!! tip "Keep console access"
    The first apply on a device should be done with console or MAC-level access available. The refusals cover the cases the plan can see; they cannot see a firewall rule or a path outside this provider's types.

## From `www` to HTTPS and a Let's Encrypt certificate

A new device serves REST on `www` (plain HTTP). The `certificate` type creates a self-signed certificate on the device and signs it, so `www-ssl` and `api-ssl` can serve with it. The create is one `PUT /rest/certificate`, the signing a second step, `POST /rest/certificate/sign`. A declared certificate that exists but is unsigned (a run that stopped between the two) plans a lone signing step, so the next apply finishes it. RouterOS cannot change a signed certificate's subject or key: a difference in any field but `comment` is a warning, never a write. Set `absent: true` and recreate it under a new name.

```yaml
resources:
  - {type: certificate, name: bootstrap-https, common-name: router.example.com, key-usage: [digital-signature, key-encipherment, key-cert-sign, tls-server], days-valid: 365}
  - {type: ip.service, name: www-ssl, certificate: bootstrap-https, disabled: false}
  - {type: ip.service, name: api-ssl, certificate: bootstrap-https, disabled: false}
```

The order below never cuts the connection that applies the change:

1. With `api_url: http://192.0.2.2`, declare the certificate and the two services as above, leave `www` alone and apply. `www` still carries the connection.
2. Confirm HTTPS answers (`curl -sk -o /dev/null -w '%{http_code}' https://192.0.2.2/rest/system/resource` prints `401`), then run `infra doctor`.
3. Switch `api_url` to `https://192.0.2.2` with `verify_ssl: false`, then run `infra doctor` and `infra plan` (clean).
4. Install the Let's Encrypt certificate (#1683), set `verify_ssl: true` and point `www-ssl` and `api-ssl` at the installed certificate.
5. Optionally disable `www`, which the plan allows once `api_url` is `https`.

**Why `verify_ssl: false`, and no pin.** The bootstrap certificate lives only until the Let's Encrypt certificate replaces it, and a pin would have to be redone at that replacement. The state it replaces is plain HTTP with basic auth, so unverified TLS is still better. Revert `verify_ssl` to `true` after step 4.

**Timeout.** Signing blocks the REST call while the device generates the key; raise `timeout` for large keys.

!!! warning "Not yet live-verified"
    The field names of the create, the `sign` call with `number` set to the row's `.id`, and a non-empty `fingerprint` marking a signed row are taken from the RouterOS manuals and have not been checked on a device. The live check of #1683 verifies them.

## Apply and Destroy

`infra apply` plans against the live device in the same run, then writes the steps in phase order (A to F, see the ADR). Each step is one REST call: `PUT` to create, `PATCH` to update, `DELETE` to remove. The run stops at the first error, because later steps assume the earlier ones took effect.

- **Refusals are re-checked.** An apply whose plan carries refusals sends nothing, and the error lists the reasons.
- **A failure names the step.** The error gives the step number out of the total, its phase, kind, type and resource name, RouterOS's message, and the steps that already ran. If the device stops answering mid-run, the error says so and asks you to check console access before running again. Steps already completed stay in effect and are reported as outcomes.
- **Created objects.** A step that acts on an object created earlier in the run (for example enabling VLAN filtering on a new bridge) uses the `.id` RouterOS returned for the create, or re-reads the path once to find it.
- **Deletes follow the managed set.** A full apply deletes an undeclared object only when InfraFoundry applied it before (ADR-0018). Each such name is released from the managed set afterwards. A managed row that no longer parses is kept. A targeted or add-only run deletes and releases nothing.
- **Outcomes.** Each object reports one outcome, `create`, `update` or `delete`, as `mikrotik_<type>.<name>` (a bridge created and then switched to VLAN filtering reports `create`).

`infra destroy` removes the objects declared in your YAML that exist on the device, in reverse dependency order. It never touches:

- `ip.service` entries, which cannot be deleted;
- `absent: true` entries;
- objects that are not in your YAML;
- built-in or dynamic rows.

`--target` narrows the set. The end state goes through the same management-path check as a plan, so a destroy that would remove the management address or path is refused whole, before any write. Destroying an environment whose YAML holds the management path therefore needs console access and is refused by design.

## Drift Detection

`infra drift detect` plans the device add-only through the same runner. A live object that differs from your YAML (for example an out-of-band PVID change on a managed port) is reported and fires `DRIFT_DETECTED`. Undeclared objects are not reported as drift, because drift runs never delete.

Drift runs make no update check and never contact the vendor.

## RouterOS and RouterBOARD Updates

A `system.package.update` resource marks the device whose RouterOS follows the latest release of an update channel ([ADR-0037](../decisions/0037-mikrotik-routeros-is-upgraded-to-the-latest-release-of-a-channel-by-a-provider-command.md)). Its only field is `channel`: `stable` (default), `long-term`, `testing` or `development`. A version cannot be pinned, and only one is allowed per environment.

```yaml
# envs/lab/resources/routeros-update.yaml
resources:
  - name: routeros
    type: system.package.update
    provider: mikrotik
    channel: stable
```

`infra plan` only reports, for example:

```text
mikrotik_rest: system.package.update 'routeros': up to date (7.25)
mikrotik_rest: system.package.update 'routeros': 7.24 → 7.25 available (run foundry provider mikrotik upgrade --env lab)
mikrotik_rest: system.package.update 'routeros': up to date (7.25); RouterBOARD firmware 7.20 → 7.25 pending (run foundry provider mikrotik upgrade --env lab)
```

A failed check is a warning and never fails the plan. `infra apply`, `infra destroy` and drift runs never install, flash or reboot.

### The upgrade command

```bash
foundry provider mikrotik upgrade --env lab
foundry provider mikrotik upgrade --env lab --yes --lock-timeout 60
```

There is no `--device`: one device per environment. The command holds the environment lock, checks read-only, asks once (unless `--yes`), runs the stages and re-plans. It runs two stages, each with its own deadline of `upgrade_timeout` seconds, because each ends in a reboot:

1. **RouterOS**, when the channel offers a newer release: `install`, wait for the device to go down and come back, then verify the installed version.
2. **RouterBOARD firmware** (the bootloader), when `current-firmware` differs from `upgrade-firmware` (it lags the packages on real hardware, and runs alone when RouterOS is already current): `routerboard/upgrade`, `reboot`, wait, verify. It is skipped on a device without RouterBOARD firmware, such as a CHR.

Success is proven by polling for the device going down and coming back and by re-reading the versions, not by the replies of the write calls. A failure names the step (`check`, `install`, `reboot-wait`, `verify-routeros`, `routerboard-upgrade`, `reboot` or `verify-routerboard`) and the versions the device reports, and says that a flash cannot be rolled back automatically.

**Channel switch.** RouterOS checks the channel set on the device. When it differs from the declared one, the plan warns and makes no update check, and the command's table shows both channels and no available version. Nothing is written before the confirmation; afterwards the command sets the channel, checks, and upgrades without asking again if a release is offered.

!!! warning "Run it from a path that does not cross the switch"
    Run the command from a machine that reaches the management address directly, not over a path through the switch's own uplink, or the polling loses its connection for the whole outage.

!!! warning "Plan the outage"
    Each reboot interrupts traffic through the device (one or two reboots per run). On a WAN-edge switch that cuts internet access for everything behind the firewalls for each reboot, while LAN and inter-VLAN traffic that does not cross the switch keeps working. An HA or CARP pair gives no protection when both firewalls' WAN links run through this one switch. Run the command when the outage is acceptable.

### Verification status

Verified read-only against a RouterOS 7.25 device: `GET system/package/update` (no `latest-version` or `status` until a check has run), `POST system/package/update/check-for-updates` (a list of progress sections, the last one carries the result; status "New version is available") and `GET system/routerboard`.

**Verified live on a RouterOS 7.25.1 CHR (#1665):** `foundry provider mikrotik upgrade` took the CHR from 7.25.1 to 7.25.2 in one run of about 15 seconds. `POST system/package/update/install` installed the release and rebooted the device once (the log shows `installed system-7.25.2` and `router rebooted by api`). The command saw it go down and come back, verified the version and re-planned "up to date (7.25.2)". The "up to date" status string is `System is already up to date`. `POST system/package/update/set {"channel": ...}` returns `[]` and the channel reads back changed. On a CHR, `GET system/routerboard` returns API 400 (`no such command or directory`), which the command treats as "no RouterBOARD firmware" and skips stage 2.

**Not yet verified:** `POST system/routerboard/upgrade` and `POST system/reboot`, which need RouterBOARD hardware; a CHR has neither. The first run on a hardware switch exercises them. The command ignores the replies of the write calls apart from their HTTP status and proves each stage by polling and re-reading the versions, so a different reply shape cannot report a failed stage as a success.

## Doctor

`infra doctor` checks the schema (including `system.package.update`), the settings (including `upgrade_timeout`) and their secret references, that the device answers `/rest/system/resource` with RouterOS 7 or later, and that every interface a resource references exists on the device or is declared.

## Test target: a CHR VM

The `routeros-chr` blueprint (`blueprints/routeros-chr/`) builds a disposable
RouterOS Cloud Hosted Router on Proxmox, so the provider can be tried without a
real switch. It imports MikroTik's `.img.zip` image, attaches a management NIC
(`ether1`) and trunk NICs (`ether2`..), and bootstraps the VM over its serial
console: admin password, optional static address, and the `www` service. With `https_bootstrap: true` it also creates and signs a self-signed `bootstrap-https` certificate and enables `www-ssl` and `api-ssl` with it (`www` stays on); see [From `www` to HTTPS](#from-www-to-https-and-a-lets-encrypt-certificate).
`infra destroy` removes the VM. The bootstrap is verified against a RouterOS
7.25.1 CHR; the blueprint README lists what was checked.

Point the environment at the VM (the example package sets a static address):

```yaml
provider_settings:
  mikrotik:
    api_url: http://192.0.2.241
    username: admin
    password: secret://env_secrets/mikrotik/password
```

The bootstrap enables `www` (plain HTTP) because `www-ssl` needs a certificate
on the box; `https_bootstrap: true` adds one. `infra doctor` warns about plaintext HTTP; that is expected for a
disposable test VM. CHR's free licence caps throughput, which is enough for API
testing. See `blueprints/routeros-chr/README.md` for the variables.

## Limitations

- One device per environment.
- `config migrate` extractors and the `/export terse` backup are separate work.
