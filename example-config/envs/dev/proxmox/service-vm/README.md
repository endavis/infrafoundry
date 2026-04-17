# service-vm (example consumer)

Example thin-instantiation of the `service-vm` blueprint. Deploys a single
infrastructure VM on Proxmox, a matching OPNsense DHCP reservation, and no
NFS mount (the default).

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
- `nfs_server` is left at its empty default, so no `proxmox.storage`
  resource is emitted. To add an NFS mount, set `nfs_server` and
  `nfs_export` in `variables:`.
