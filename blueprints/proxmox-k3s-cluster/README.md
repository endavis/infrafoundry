# Proxmox k3s Cluster Blueprint

Reusable blueprint that deploys a k3s Kubernetes cluster on Rocky 9 Proxmox VMs:
one server (control plane + etcd) plus an arbitrary number of agent (worker)
nodes. Creates the VMs, configures OPNsense Kea DHCP reservations for every
node, and runs a multi-phase post-deploy event handler that installs k3s on the
server, joins each agent, verifies the cluster, and writes a local kubeconfig.

This blueprint clones from the `rocky9-template` blueprint. See
`blueprints/rocky9-template/README.md` for the upstream template, and
`blueprints/aiqum/README.md` for the closest structural reference (multi-file
blueprint with cross-provider resources and a scripted on_create handler).

## What's new in this blueprint

This is the first InfraFoundry blueprint to use **Jinja loops over a list of
dicts** in resource files. The agent count is variable: the consumer supplies
an `agents:` list and `vm.yaml` / `dhcp.yaml` iterate it with
`{% for agent in agents %}`. Both files render normally with `agents: []`,
producing only the server entries.

## Usage

A package consumes this blueprint with a thin manifest that supplies only the
per-instance values:

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: k3s-cluster
description: "k3s Kubernetes cluster"
blueprint: proxmox-k3s-cluster

variables:
  cluster_name: my-k3s
  disk_storage: local-lvm
  dhcp_subnet: my-subnet

  # Optional: route SSH through a bastion. Omit for direct SSH.
  # jumphost: "ansible@jump.example.com"

  # --- Server node ---
  server_name: my-k3s-server
  server_vmid: 230
  server_target: pve1
  server_mac: "BC:24:11:00:07:00"
  server_ip: "192.168.10.70"

  # --- Agent nodes (1 or more) ---
  agents:
    - name: my-k3s-agent-1
      vmid: 231
      target_node: pve1
      mac: "BC:24:11:00:07:01"
      ip: "192.168.10.71"
    - name: my-k3s-agent-2
      vmid: 232
      target_node: pve2
      mac: "BC:24:11:00:07:02"
      ip: "192.168.10.72"
```

Then:

```bash
infra apply --env <env> --package k3s-cluster
```

## Variables

### Required (must be set in the consuming package)

| Variable | Description | Example |
|---|---|---|
| `disk_storage` | Proxmox storage pool for VM disks | `local-lvm` |
| `dhcp_subnet` | OPNsense Kea subnet reference | `opt1-infrastructure` |
| `server_name` | Server VM hostname | `k3s-server` |
| `server_vmid` | Server Proxmox VM ID | `230` |
| `server_target` | Proxmox host for the server VM | `pve1` |
| `server_mac` | Server VM MAC address | `BC:24:11:00:07:00` |
| `server_ip` | Server VM IP (assigned via DHCP reservation) | `192.168.10.70` |
| `agents` | List of agent node dicts (see schema below) | (list) |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `cluster_name` | `k3s-cluster` | Logical cluster name; used in the kubeconfig filename |
| `template_vmid` | `901` | Rocky 9 cloud-init template VM ID |
| `template_node` | `pve1` | Proxmox node hosting the template (for cross-node clones) |
| `cores` | `2` | vCPU count per VM |
| `memory` | `4096` | Memory in MiB per VM |
| `disk_size` | `56` | Disk size in GiB per VM |
| `bridge` | `vmbr0` | Network bridge |
| `vlan_tag` | `10` | VLAN tag for the VM NIC |
| `jumphost` | `""` (direct SSH) | SSH jumphost for VM access during install. When empty, the post-deploy script SSHes directly from the InfraFoundry host to each node. Set to e.g. `ansible@jump.example.com` to tunnel through a bastion. |
| `k3s_server_args` | `--disable traefik --disable servicelb` | Extra flags for the k3s server installer |
| `kubeconfig_local_path` | `~/.kube/{{ cluster_name }}.yaml` | Local destination for the fetched kubeconfig |

### Agent dict schema

Each entry in the `agents:` list must be a mapping with these fields:

| Field | Description | Example |
|---|---|---|
| `name` | Agent VM hostname | `k3s-agent-1` |
| `vmid` | Agent Proxmox VM ID | `231` |
| `target_node` | Proxmox host for the agent VM | `pve1` |
| `mac` | Agent VM MAC address | `BC:24:11:00:07:01` |
| `ip` | Agent VM IP (assigned via DHCP reservation) | `192.168.10.71` |

The blueprint supports zero agents (empty list) for a single-node cluster.

## Prerequisites

- The `rocky9-template` blueprint applied (provides the template VM to clone from)
- An OPNsense Kea subnet reference matching `dhcp_subnet`
- SSH access from the InfraFoundry host to every target VM as the `ansible`
  user (provided by the rocky9-template cloud-init). Either direct (default)
  or via an SSH jumphost — see the `jumphost` variable.
- `jq` and `bash 4+` available on the InfraFoundry host (post-deploy script
  uses `mapfile` and `jq -r '.agents[]'` to iterate the agent list)

## Automation Flow

```
infra apply --package k3s-cluster
  |
  +-- Terraform: Clone Rocky 9 template for the server + each agent
  +-- Terraform: Create DHCP reservations on OPNsense for every node
  |
  +-- on_create (resource: <server_name>):
       |
       +-- k3s-post-terraform.sh
            |
            +-- Phase 1: Wait for every VM to be SSH-reachable via jumphost
            +-- Phase 2: Prepare nodes (kernel modules, sysctl, firewalld off,
            |             MinIO data dir)
            +-- Phase 3: Install k3s server with k3s_server_args
            +-- Phase 4: Retrieve join token, install k3s agent on each agent
            +-- Phase 5: Verify all (1 + N) nodes report Ready
            +-- Phase 6: Fetch kubeconfig, rewrite to server IP, save locally
```

## Notes

- VM hardware (`cores`, `memory`, `disk_size`) is set to sensible homelab
  defaults and is rarely overridden.
- The `tags: [k3s, k3s-server]` / `[k3s, k3s-agent]` and `cloud_init_snippets`
  are recipe-level metadata baked into the blueprint.
- Events live at the top of `blueprint.yaml` (not embedded in `vm.yaml`)
  because the shorthand `vms:` format does not extract per-resource events.
- The `requires:` field of the on_create handler lists only the server VM.
  All agent VMs are created in the same terraform apply, so the handler fires
  once after the apply completes regardless of agent count.
- The post-deploy script reads `INFRAFOUNDRY_PACKAGE_VARS` (the JSON-serialized
  full variable dict) via `jq` to iterate the agents list. This pattern lets a
  bash script handle variable cardinality without templating the script itself.
