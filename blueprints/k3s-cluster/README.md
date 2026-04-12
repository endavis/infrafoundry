# k3s Cluster Blueprint (Multi-Provider)

Unified blueprint that deploys a k3s Kubernetes cluster on either **Proxmox**
(Rocky 9 VMs) or **OCI** (ARM Always-Free-Tier instances with Tailscale
overlay). The consumer selects the provider via the package's `provider` field
or directory placement; the blueprint supplies provider-specific defaults,
resources, and event handlers automatically.

This blueprint supersedes the previous `proxmox-k3s-cluster` and
`oci-k3s-cluster` blueprints. Both provider variants are now served from a
single blueprint using the multi-provider `providers:` section introduced in
issue #507.

## Provider Variants

### Proxmox

One server (control plane + etcd) plus N agent (worker) nodes on Rocky 9 VMs.
Creates the VMs, configures OPNsense Kea DHCP reservations for every node, and
runs a multi-phase post-deploy script that installs k3s, joins each agent,
verifies the cluster, and writes a local kubeconfig.

### OCI

One control plane plus N worker nodes on OCI ARM instances. Creates a VCN with
public and private subnets, provisions compute instances with Tailscale
cloud-init, then runs ansible-playbook against the shared k3s-server /
k3s-agent roles.

## Usage

### Proxmox

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: k3s-cluster
description: "k3s Kubernetes cluster"
blueprint: k3s-cluster

variables:
  cluster_name: my-k3s
  disk_storage: local-lvm
  dhcp_subnet: my-subnet
  server_name: my-k3s-server
  server_vmid: 230
  server_target: pve1
  server_mac: "BC:24:11:00:07:00"
  server_ip: "192.168.10.70"
  agents:
    - name: my-k3s-agent-1
      vmid: 231
      target_node: pve1
      mac: "BC:24:11:00:07:01"
      ip: "192.168.10.71"
```

### OCI

```yaml
# envs/<env>/<package>/infrafoundry.yml
name: k3s-cluster
description: "OCI k3s cluster"
blueprint: k3s-cluster
provider: oci

variables:
  cluster_name: my-k3s
  control_name: my-k3s-control
  image: "ocid1.image.oc1.iad.aaaaaaa..."
  ssh_public_key: "ssh-rsa AAAA... user@host"
  tailnet: "tail-abcde.ts.net"
```

## Directory Layout

```
k3s-cluster/
  blueprint.yaml           # Shared defaults + providers section
  playbook.yml             # Ansible playbook (OCI variant)
  providers/
    proxmox/
      vm.yaml              # Proxmox VM resource template
      dhcp.yaml            # OPNsense DHCP reservation template
    oci/
      instance.yaml        # OCI compute instance template
      network.yaml         # OCI VCN + subnet template
  scripts/
    proxmox/
      k3s-post-terraform.sh
    oci/
      k3s-post-terraform.sh
      cleanup-tailscale-devices.sh
      verify-cluster.sh
```

## Variables

See the original blueprint READMEs for the full variable reference:
- Proxmox variables are documented in the `providers.proxmox.defaults` section
  of `blueprint.yaml`
- OCI variables are documented in the `providers.oci.defaults` section of
  `blueprint.yaml`

Shared defaults (`cluster_name`, `k3s_version`, `k3s_server_args`) are at the
top level and apply to both providers.
