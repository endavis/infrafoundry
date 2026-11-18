---
title: "OpenWrt Provider"
description: "Manage an OpenWrt device over SSH with generated community.openwrt playbooks, a check-mode plan and ubus apply with automatic rollback"
audience:
  - users
tags:
  - providers
---

# OpenWrt Provider

The OpenWrt provider manages one OpenWrt device (stock OpenWrt or a vendor build such as GL.iNet) through UCI. It generates an Ansible playbook for the [`community.openwrt`](https://galaxy.ansible.com/ui/repo/published/community/openwrt/) collection and runs it with `ansible-playbook`. It does not generate Terraform. The decision and the rejected alternatives are in [ADR-0028](../decisions/0028-openwrt-devices-are-managed-through-generated-communityopenwrt-playbooks-with-ubus-apply-rollback.md).

For a read-only backup of a device InfraFoundry does not manage, see [Device config collectors](../guides/device-config-collectors.md) (`openwrt-ssh`).

!!! note "Live verification"
    Verified on a GL.iNet device running OpenWrt 23.05:

    - a check-mode plan wrote nothing to the device;
    - an apply changed a DHCP pool, confirmed it, and the change outlasted the rollback timeout;
    - a second apply restored the old value, and the re-plan was clean.

    Not yet verified:

    - stock OpenWrt;
    - an apply that loses the connection and rolls back;
    - a management-address change.

    Which services reload after an apply was not measured. Keep console or power access for the first apply on new hardware.

## Requirements

- `ansible-playbook` on the controller (the `ansible` dependency of InfraFoundry provides it).
- The `community.openwrt` collection, version 1.11.0 or later. The provider declares it, so `foundry deps check --env <env>` reports it and `foundry deps sync --env <env>` installs it.
- Key-based SSH to the device as a user that can run `uci` and `ubus` (normally `root`). Host-key checking is always on, even when `ANSIBLE_HOST_KEY_CHECKING=False` is set in the environment: add the host key first with `ssh-keyscan` or a first manual login.
- No Python on the device. The collection's modules run in `ucode`, which `infra doctor` checks for at `/usr/bin/ucode`.
- On the device, `ubus call uci apply` must accept `rollback` and `uci confirm` must exist. `infra doctor` checks both.

## Settings

One device per environment, under `provider_settings.openwrt` in `envs/<env>/settings.yaml`:

```yaml
providers:
  - openwrt

provider_settings:
  openwrt:
    address: 192.0.2.2
    ssh_user: root                    # default
    ssh_port: 22                      # default
    ssh_private_key_file: ~/.ssh/example_key
    rollback_timeout: 90              # seconds, 30-600, default 90
    connect_timeout: 10               # seconds, default 10
```

`secret://env_secrets/...` references resolve from the environment's SOPS secrets. The provider stores no password.

Several devices per environment are not supported yet.

## Supported Resources

Declare resources in the resource-centric format. Field names are the UCI option names, with the exceptions noted below. Resource names must be unique within the provider, so two resources for the same interface need different names and an explicit `interface`.

| Type | UCI section | Identity key | Deletable |
|------|-------------|--------------|-----------|
| `network.interface` | `network.<interface>` (a named section) | `interface`, default the resource name | no |
| `dhcp.pool` | `dhcp` section of type `dhcp` | `interface`, default the resource name | no |
| `dhcp.host` | `dhcp` section of type `host` (a static lease) | `mac` | yes |
| `firewall.redirect` | `firewall` section of type `redirect` (a port forward) | `name`, default the resource name | yes |

```yaml
# envs/travel/resources/router.yaml
resources:
  - name: lan-interface
    provider: openwrt
    type: network.interface
    config:
      interface: lan
      ipaddr: 192.0.2.1
      netmask: 255.255.255.0

  - name: lan-dhcp
    provider: openwrt
    type: dhcp.pool
    config:
      interface: lan
      start: 100
      limit: 150
      leasetime: 12h

  - name: printer
    provider: openwrt
    type: dhcp.host
    config:
      mac: 02:00:00:00:00:0a
      ip: 192.0.2.50
      hostname: printer-1      # the UCI option "name"
      leasetime: 12h

  - name: web
    provider: openwrt
    type: firewall.redirect
    config:
      src_dport: 8080
      dest_ip: 192.0.2.50
      dest_port: 80            # src: wan, dest: lan, proto: tcp udp, target: DNAT by default
```

Notes on the fields:

- `network.interface`: `ipaddr` must be a plain IPv4 address with a separate dotted `netmask`; CIDR is rejected. `proto` is optional and left alone when absent.
- `dhcp.host`: `hostname` sets the UCI option `name`, because the resource loaders copy the resource name into `config.name`. `absent: true` deletes the lease.
- `firewall.redirect`: `absent: true` deletes the forward. `enabled` is a boolean.
- Values compare as UCI stores them: integers as `"100"`, booleans as `"1"` and `"0"`, `proto` as a space-joined string. A converged device plans clean.
- Text values may not contain control characters or Jinja markers (`{{`, `{%`, `{#`), because they end up in a generated playbook.

## Matching and adoption

Every write uses `community.openwrt.uci` with `command: section` and `replace: false`, so options you set in the vendor UI and do not declare survive.

- `network.interface` is a named section (`network.lan`).
- A lease is matched by `mac` and created anonymous. A lease made in the vendor UI is adopted, never renamed.
- A port forward is matched by its `name` option, the same way.

Before each lease, the playbook fails the run when more than one `host` section has the MAC, or when a section has the MAC in the other letter case (`uci` compares strings exactly, so it would create a second lease). Fix the device, or use one spelling.

## Plan and diff

`infra plan` runs the playbook with `--check --diff`. Nothing is written to the device. The plan reports, per resource, whether it would change.

An unchanged resource that InfraFoundry does not manage yet is adopted into state on the next apply. This produces no device change and no plan change.

`infra drift detect` runs the same check pass, add-only. A value changed on the device out of band shows as drift.

## Apply and rollback

`infra apply` runs the check pass first and refuses a plan that could cut the management connection (see below). Then it runs the playbook for real:

1. A preflight fails the run when UCI changes are already pending on the device, so InfraFoundry never commits someone else's staged edits.
2. The `uci` tasks stage the changes without committing.
3. The playbook creates an rpcd session, grants it the `uci` scope, moves the staged config files into the session's save directory and reverts the staging in the default cursor.
4. `ubus call uci apply` commits with `rollback` and the configured `rollback_timeout`.
5. The playbook resets the SSH connection, waits for the device (the timeout minus 15 seconds), then sends `ubus call uci confirm` and destroys the session.

If the device cannot be reached after the apply, nothing confirms, and the device reverts the change by itself when the timeout runs out. The result then says that the device did not confirm and reverts by itself (marker `INFRAFOUNDRY_ROLLBACK_PENDING` in the output). If the run fails before the apply was reached, a rescue reverts the staged changes and destroys the session.

## Management-change refusal

A change to a `network.interface` is a management change when the settings `address` is in the interface's subnet before or after the change, when the address does not resolve to an IPv4 address, or when the change cannot be read from the check output. It is refused at plan time unless the resource sets `confirm_management_change: true`.

With the flag, and the settings `address` equal to the interface's current `ipaddr`, the run reconnects to the new `ipaddr` before it confirms. If it cannot, the device rolls back.

A `firewall.redirect` whose `src_dport` covers the settings `ssh_port` on the `wan` zone is refused offline in the same way, because it can take over SSH. Set `confirm_management_change: true` to allow it.

## Destroy and the managed set

`infra destroy` deletes the declared `dhcp.host` and `firewall.redirect` objects and only forgets `network.interface` and `dhcp.pool` (the sections stay on the device).

InfraFoundry deletes an undeclared object only when it applied that object before ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). A managed lease or port forward that is no longer in the YAML is deleted; a managed interface or pool is only forgotten. Both are skipped under `--add-only` and when `-r` narrows the run. Objects you made on the device stay untouched.

## Out of scope

- Wireless, system, and any config other than `network`, `dhcp` and `firewall`.
- Several devices per environment.
- Terraform.

## Stock OpenWrt and GL.iNet

The collection targets stock OpenWrt. GL.iNet builds are OpenWrt with a vendor UI on top; the lease and port-forward adoption above is what lets the two coexist. Vendor UIs may rewrite parts of the same configs, so declare only what you manage.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `UCI changes are already pending` | Someone staged edits on the device. Commit or `uci revert` them. |
| `more than one dhcp host section has MAC ...` | Duplicate leases on the device. Remove one. |
| `a dhcp host section already has MAC ...` | The device stores the MAC in the other letter case. Use that spelling. |
| `... refused, it could cut the management connection` | See [Management-change refusal](#management-change-refusal). |
| `the device did not confirm the change and reverts it by itself` | The device was unreachable after the apply. Check it, then run again. |
