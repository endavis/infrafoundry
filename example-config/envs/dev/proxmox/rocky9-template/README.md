# Rocky Linux 9 Cloud Image Template

Creates a Proxmox VM template from the Rocky Linux 9 GenericCloud qcow2 image.
VMs cloned from this template support cloud-init for automated user, network,
and package configuration.

## Quick Start

```bash
# Create the template
infra apply --env dev --package rocky9-template

# Destroy the template
infra destroy --env dev --package rocky9-template
```

## What It Does

1. **Downloads** the Rocky 9 GenericCloud qcow2 image to Proxmox storage
2. **Creates** a VM template with:
   - `virtio-scsi-pci` disk controller (scsi0)
   - Cloud-init drive for user/network injection
   - Default user `rocky` with cloud-init
   - DHCP networking via cloud-init
   - qemu-guest-agent enabled

## Configuration

Edit `infrafoundry.yml`:

| Variable | Description | Default |
|---|---|---|
| `template_name` | Template VM name | `rocky9-template` |
| `vmid` | Proxmox VM ID | `901` |
| `target_node` | Proxmox host to create on | `pve1` |
| `storage` | Proxmox storage for disk | `local-lvm` |

## Package Structure

```
rocky9-template/
  infrafoundry.yml    # Config — edit this
  resources.yaml      # Template resource definition
  README.md           # This file
```

## Cloning VMs from This Template

Other packages clone from this template by referencing its VM ID:

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
