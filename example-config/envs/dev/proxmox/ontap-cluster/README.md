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

## Publishing DNS names

Set `publish_dns: true` and `dns_domain` in `infrafoundry.yml` to create an
OPNsense Unbound host override for each reserved IP: the cluster management LIF,
both node management addresses and both data LIFs, named `<hostname>-dns`
(for example `ontapcl-dev-dns`). The overrides use `dns_publish_domain`, or
`dns_domain` when that is empty; one of the two is required with `publish_dns`.
`dns_domain` also stays ONTAP's DNS search domain, so set `dns_publish_domain`
when the OPNsense zone differs from it (#1267). Clients must reach this
OPNsense box's Unbound directly, or through an `unbound.forwards` entry for the
published domain (#1168). Turning `publish_dns` off may leave the last override on the box
(#1252).

## Cluster interconnect MTU

`cluster_mtu` (default `1500`) sets the MTU of the ONTAP `Cluster` broadcast
domain. The simulator ships with 9000, which drops cluster packets (EMS
`vifmgr.cluscheck.ctdpktloss`) on any network below that. 1500 works anywhere.
Raise it only when the network under the cluster ports (`e0a`/`e0b`) is jumbo
end to end.

## Verifying the cluster certificate

By default the blueprint does not verify the cluster's TLS certificate on its
ONTAP REST calls. That is a lab-only opt-out. Set `ontap_ca_cert` to the
absolute path of a PEM file (`~` is allowed, for example `~/ontap-ca.pem`) that
trusts the cluster management certificate, and every ONTAP call checks the
certificate against it. A missing file stops the run before anything is touched.

The certificate must name `cluster_mgmt_ip`. The simulator creates its own
self-signed certificate when the cluster is created, so leave `ontap_ca_cert`
empty for a fresh build. To turn verification on afterwards, install a
certificate signed by your CA on the cluster, set `ontap_ca_cert` and re-run:
the probe skips a cluster that already exists. A certificate the CA does not
trust stops the run with a message naming `ontap_ca_cert`.

## Adding the cluster to the NetApp Console

After setup, the cluster can add itself to the NetApp Console through a
registered Console agent (see the `console-connector` blueprint). Set the client ID,
secret and one agent input, or none to skip:

| Variable | Where | Value |
|---|---|---|
| `console_client_id` | `secrets.yaml` | Service account client ID (admin role) |
| `console_client_secret` | `secrets.yaml` | Service account secret |
| `console_agent_id` | `infrafoundry.yml` | Optional. The agent's `agentId`; empty: looked up by `console_agent_address` |
| `console_agent_address` | `infrafoundry.yml` | Optional. The agent VM's address (the connector's `ip_address`, e.g. `192.0.2.51`) |

Optional: `console_account_id` and `console_workspace_id`, needed only when the
service account sees more than one organization or workspace. Also optional are
`console_system_name` (default `cluster_name`) and `console_cluster_user`
(default `admin`, with `ontap_password`).

The step, `blueprints/ontap-cluster/scripts/ontap-console-discover.py`, runs on the InfraFoundry host and
needs HTTPS to `netapp-cloud-account.auth0.com` and `api.bluexp.netapp.com`
only. The Console forwards the request to the agent, and the agent connects to
`cluster_mgmt_ip`. A cluster already in the Console, matched by name or
management address, is left alone. With `console_agent_address`, the script finds the
agent ID in the Console's agent list (an undocumented endpoint the Console web UI uses)
and needs exactly one active agent at that address. `infra destroy` removes the cluster
from the Console again (`--remove`). Destroy the cluster before the connector, in a
separate run.

To add a cluster that already exists without rebuilding it, run the script
with `INFRAFOUNDRY_PACKAGE_VARS` set to a JSON object holding `cluster_name`,
`cluster_mgmt_ip`, `ontap_password` and the `console_*` values.
