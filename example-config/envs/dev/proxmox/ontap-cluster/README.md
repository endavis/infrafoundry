# ONTAP Simulator 2-Node Cluster (example)

Example consumer of the `ontap-cluster` blueprint. Deploys a 2-node NetApp ONTAP
Simulator cluster on Proxmox with fully automated cluster setup via Ansible.
**Update IPs, VM IDs, OVA path, and the DHCP subnet for your environment before
applying.**

```bash
foundry -c example-config infra apply --env dev --package ontap-cluster
```

See `blueprints/ontap-cluster/README.md` for the full variable reference,
prerequisites, and the description of the post-deploy event handler.
