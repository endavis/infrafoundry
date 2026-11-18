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

!!! warning "Plan only for now"
    `infra plan`, `infra doctor` and `infra drift detect` work. `infra apply` and `infra destroy` fail with `mikrotik apply is not implemented yet (see #1483)` until the follow-up lands (#1483). An apply therefore never silently does nothing.

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
```

`secret://env_secrets/...` references resolve from the environment's SOPS secrets. The password never appears in logs or error messages.

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
| `ip.service` | `/rest/ip/service` | `name`; update only, never created or deleted |

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
| B | Creates in dependency order; bridge VLAN membership widened to old and new; port PVID updates on bridges whose filtering is off at that moment |
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

If the host cannot be resolved and the plan touches bridge, VLAN or address types, the plan refuses.

!!! tip "Keep console access"
    The first apply on a device should be done with console or MAC-level access available. The refusals cover the cases the plan can see; they cannot see a firewall rule or a path outside this provider's types.

## Drift Detection

`infra drift detect` plans the device add-only through the same runner. A live object that differs from your YAML (for example an out-of-band PVID change on a managed port) is reported and fires `DRIFT_DETECTED`. Undeclared objects are not reported as drift, because drift runs never delete.

## Doctor

`infra doctor` checks the schema, the settings and their secret references, that the device answers `/rest/system/resource` with RouterOS 7 or later, and that every interface a resource references exists on the device or is declared.

## Limitations

- One device per environment.
- Apply and destroy: #1483.
- `config migrate` extractors and the `/export terse` backup are separate work.
