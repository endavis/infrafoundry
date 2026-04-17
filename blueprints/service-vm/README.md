# service-vm Blueprint

Reusable blueprint for lightweight infrastructure service VMs. It clones a
Proxmox template and creates an OPNsense DHCP reservation. Typical
consumers are bastion hosts, log aggregators, internal web servers, CI
runners, or any "single VM plus DHCP" deployment.

This sits one tier above the framework-bundled `basic-vm` blueprint
(`src/infrafoundry/core/blueprints/basic-vm/`): it adds a DHCP
reservation, cloud-init snippet wiring, and multi-instance safety. Use
`basic-vm` when you just want a throwaway template scaffold; use
`service-vm` when you want a reusable, DHCP-integrated service node.

> **Guest-level NFS mounts** belong in a cloud-init snippet on the VM
> (see `packages/nginx-nfs` in the example config). **Proxmox-level NFS
> storage pools** are cluster-wide resources and should live in a
> dedicated storage package, not inside per-VM blueprints like this one.

## Usage

A package consumes this blueprint with a thin manifest that supplies only
the per-instance values:

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: my-service
description: "My infrastructure service VM"
blueprint: service-vm

variables:
  vm_name: my-service
  vmid: 210
  target_node: pve1
  mac_address: "BC:24:11:F8:F4:7D"
  ip_address: "192.168.10.60"
  dhcp_subnet: opt1-infrastructure
  cloud_init_snippets:
    - system/hostname
    - users/ansible
    - network/dhcp
    - packages/qemu-agent
  tags: ["infra", "web"]
```

Then:

```bash
foundry infra apply --env <env> --package my-service
```

## Variables

### Required (must be set in the consuming package)

| Variable        | Description                                                         | Example                |
| --------------- | ------------------------------------------------------------------- | ---------------------- |
| `vm_name`       | VM hostname (also DHCP hostname, storage mount name, etc.)          | `infra-web`            |
| `vmid`          | Proxmox VM ID                                                       | `210`                  |
| `target_node`   | Proxmox host to place the VM on                                     | `pve1`                 |
| `mac_address`   | VM NIC MAC address (also used for DHCP reservation, lowercased)     | `BC:24:11:F8:F4:7D`    |
| `ip_address`    | VM IP address (assigned via DHCP reservation)                       | `192.168.10.60`        |
| `dhcp_subnet`   | OPNsense Kea subnet reference                                       | `opt1-infrastructure`  |

### Optional (blueprint defaults)

| Variable                 | Default                        | Description                                            |
| ------------------------ | ------------------------------ | ------------------------------------------------------ |
| `template_vmid`          | `900`                          | Source template VM ID to clone from                    |
| `template_node`          | `pve1`                         | Node hosting the template                              |
| `cores`                  | `2`                            | vCPU count                                             |
| `memory`                 | `2048`                         | Memory in MiB                                          |
| `disk_storage`           | `local-lvm`                    | Proxmox storage pool for the VM disk                   |
| `disk_size`              | `32`                           | Disk size in GiB                                       |
| `bridge`                 | `vmbr0`                        | Network bridge                                         |
| `vlan_tag`               | `10`                           | VLAN tag for the VM NIC                                |
| `agent`                  | `true`                         | Enable the qemu-guest-agent integration                |
| `onboot`                 | `true`                         | Start the VM automatically when the host boots         |
| `cloud_init_snippets`    | `[]`                           | List of cloud-init snippet names to attach             |
| `extra_cloud_init_vars`  | `{}`                           | Extra cloud-init vars merged with the `HOSTNAME` entry |
| `tags`                   | `[]`                           | Proxmox tags applied to the VM                         |
| `dhcp_description`       | `""` (falls back to `vm_name`) | Description written on the DHCP reservation            |

## Prerequisites

- A cloud-init-capable template (e.g. `rocky9-template` VMID `901` or
  `ubuntu-template` VMID `900`) exists on `template_node`.
- The OPNsense Kea subnet referenced by `dhcp_subnet` is defined.

## What gets created

- **Proxmox VM** (`proxmox.vm`, name `{{ vm_name }}`): cloned from the
  template, attached to `bridge`/`vlan_tag`, MAC pinned to `mac_address`,
  tagged with `tags`, optionally carrying `cloud_init_snippets` and the
  `HOSTNAME` cloud-init variable.
- **DHCP reservation** (`opnsense.kea_reservation`, name `{{ vm_name }}`):
  binds `ip_address` to `mac_address` on the `dhcp_subnet`, with
  `hostname = {{ vm_name }}` and description falling back to `vm_name`.

All resource names are templated so this blueprint is safe to instantiate
multiple times in the same environment (regression guard for #511).
