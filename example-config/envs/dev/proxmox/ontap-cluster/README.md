# ONTAP Simulator 2-Node Cluster (example)

Example consumer of the `ontap-cluster` blueprint. Deploys a 2-node NetApp ONTAP
Simulator cluster on Proxmox with fully automated cluster setup via Ansible.
**Update IPs, VM IDs, OVA path, and the DHCP subnet for your environment before
applying.**

```bash
foundry -c example-config infra apply --env dev --package ontap-cluster
```

See `blueprints/ontap-cluster/blueprint.yaml` for the full variable reference,
prerequisites, and the description of the post-deploy event handler.

## Cluster interconnect MTU

`cluster_mtu` (default `1500`) sets the MTU of the ONTAP `Cluster` broadcast
domain. The simulator ships with 9000, which drops cluster packets (EMS
`vifmgr.cluscheck.ctdpktloss`) on any network below that. 1500 works anywhere.
Raise it only when the network under the cluster ports (`e0a`/`e0b`) is jumbo
end to end.

## Adding the cluster to the NetApp Console

After setup, the cluster can add itself to the NetApp Console through a
registered Console agent (see the `console-connector` blueprint). Set all three
of these, or none to skip:

| Variable | Where | Value |
|---|---|---|
| `console_client_id` | `secrets.yaml` | Service account client ID (admin role) |
| `console_client_secret` | `secrets.yaml` | Service account secret |
| `console_agent_id` | `infrafoundry.yml` | The agent's `agentId`, from `https://<agent>/occm/api/occm/system/about` |

Optional: `console_account_id` and `console_workspace_id`, needed only when the
service account sees more than one organization or workspace. Also optional are
`console_system_name` (default `cluster_name`) and `console_cluster_user`
(default `admin`, with `ontap_password`).

The step, `blueprints/ontap-cluster/scripts/ontap-console-discover.py`, runs on the InfraFoundry host and
needs HTTPS to `netapp-cloud-account.auth0.com` and `api.bluexp.netapp.com`
only. The Console forwards the request to the agent, and the agent connects to
`cluster_mgmt_ip`. A cluster already in the Console, matched by name or
management address, is left alone. Removing it from the Console before
`infra destroy` is a manual step.

To add a cluster that already exists without rebuilding it, run the script
with `INFRAFOUNDRY_PACKAGE_VARS` set to a JSON object holding `cluster_name`,
`cluster_mgmt_ip`, `ontap_password` and the `console_*` values.
