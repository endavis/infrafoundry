# Rocky Linux 9 Cloud Image Template Blueprint

Reusable blueprint that builds a Proxmox VM template from the Rocky Linux 9
GenericCloud qcow2 image. VMs cloned from this template support cloud-init for
automated user, network, and package configuration.

This blueprint is the base most other Proxmox blueprints clone from. Sibling
blueprints live under `blueprints/` (see `blueprints/ontap-cluster/` for the
canonical structure reference).

## Usage

A package consumes this blueprint with a thin manifest that supplies only the
per-instance values:

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: rocky9-template
description: "Rocky Linux 9 cloud image template"
blueprint: rocky9-template

variables:
  vmid: 901
  target_node: pve1
  storage: local-lvm
```

Then:

```bash
infra apply --env <env> --package rocky9-template
```

## Variables

### Required (must be set in the consuming package)

| Variable | Description |
|---|---|
| `vmid` | Proxmox VM ID for the template |
| `target_node` | Proxmox host the template is created on |
| `storage` | Proxmox storage pool for the disk and cloud-init drive |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `template_name` | `rocky9-template` | Template VM name shown in the Proxmox UI |
| `cores` | `2` | vCPU count |
| `memory` | `2048` | Memory in MiB |
| `disk_size` | `32` | Root disk size in GiB |
| `bridge` | `vmbr0` | Network bridge |
| `ciuser` | `rocky` | Default cloud-init user |
| `image_url` | Rocky 9 latest qcow2 URL | Source image to download |
| `image_filename` | `Rocky-9-GenericCloud-Base.latest.x86_64.qcow2` | Local filename on Proxmox storage |

## What It Does

1. **Downloads** the Rocky 9 GenericCloud qcow2 image to Proxmox storage
2. **Creates** a VM template with:
   - `virtio-scsi-pci` disk controller (scsi0)
   - Cloud-init drive for user/network injection
   - Default user `rocky` with cloud-init
   - DHCP networking via cloud-init
   - qemu-guest-agent enabled

## Cloning VMs from This Template

Other packages clone from the resulting template by referencing its VM ID:

```yaml
# In a VM package's resource file
config:
  clone: 901              # Template VM ID
  disk:
    storage: local-lvm
    size: 50              # Resizes the cloned disk
  cloud_init_snippets:    # Inject cloud-init config
    - users/ansible
    - network/dhcp
    - packages/qemu-agent
```

## Cloud-Init Snippets

VMs cloned from this template can use cloud-init snippets stored at
`envs/{env}/files/cloud-init-snippets/`. Example snippets:

- `users/ansible` — Create ansible user with SSH key and sudo
- `network/dhcp` — Configure DHCP networking via netplan
- `packages/qemu-agent` — Install and enable qemu-guest-agent

Snippet names in configs should **not** include the `.yaml` extension —
the framework appends it automatically.

## Notes

- The template is created with `lifecycle { prevent_destroy = true }` to
  avoid accidental deletion
- The downloaded cloud image is cached on Proxmox storage — subsequent
  applies don't re-download
- Rocky 9 requires `cpu_type: host` (not `kvm64`) — this is the default
  for VMs cloned from any template
- Disk size in the template (32G) is a base size — cloned VMs can resize
  larger via their `disk.size` config
- The image URL is the upstream "latest" link and is intentionally not
  version-pinned
