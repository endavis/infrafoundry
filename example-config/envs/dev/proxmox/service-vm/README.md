# service-vm (example consumer)

Example thin-instantiation of the `service-vm` blueprint. Deploys a single
infrastructure VM on Proxmox and a matching OPNsense DHCP reservation.

The deployment logic lives in `blueprints/service-vm/`. This package only
supplies per-instance values.

See `blueprints/service-vm/README.md` for the full variable reference.

## Usage

```bash
foundry infra apply --env dev --package service-vm
```

## What this package demonstrates

- Minimal required inputs (`vm_name`, `vmid`, `target_node`, `mac_address`,
  `ip_address`, `dhcp_subnet`).
- A few common optional overrides (`cloud_init_snippets`, `tags`,
  `dhcp_description`).

Guest-level NFS mounts are handled by cloud-init snippets on the VM (see
`packages/nginx-nfs` for an example). Cluster-level Proxmox NFS storage
pools are a separate concern and belong in a dedicated storage package,
not in per-VM blueprints like `service-vm`.
