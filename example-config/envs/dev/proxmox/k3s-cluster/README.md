# k3s Cluster (example)

Example consumer of the `proxmox-k3s-cluster` blueprint. Deploys a 1-server +
2-agent k3s cluster on Proxmox with placeholder values. **Update IPs, MACs,
VM IDs, jumphost, and the DHCP subnet for your environment before applying.**

```bash
foundry -c example-config infra apply --env dev --package k3s-cluster
```

See `blueprints/proxmox-k3s-cluster/README.md` for the full variable reference,
prerequisites, and the description of the post-deploy event handler.
