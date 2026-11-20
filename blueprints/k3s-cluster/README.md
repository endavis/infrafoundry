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

When the package sets `jumphost`, the install script runs there, so the kubeconfig is
first written on the jumphost. The blueprint declares it under the handler's `outputs:`, and
InfraFoundry copies it to the same `~` path on your workstation (`~/.kube/<cluster>.yaml`
by default) once the script succeeds, so no manual `scp` is needed. The OCI variant
works with `jumphost` too: its Ansible roles ship in the blueprint's `roles/` directory,
which is copied to the jumphost with the rest of the blueprint.

### OCI

One control plane plus N worker nodes on OCI ARM instances. Creates a VCN with
public and private subnets, provisions compute instances with Tailscale
cloud-init, then runs ansible-playbook against the k3s-server / k3s-agent
roles shipped in this blueprint.

#### Roles

The `k3s-server` and `k3s-agent` roles live in `roles/` in this blueprint and are used by
default, so a config repo needs no `roles/` directory. To override them, put roles of the
same names under `envs/<env>/roles/`; they take precedence over the blueprint's. The
override applies to local runs only: the env directory is not copied to a jumphost.

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
  server_target: node1
  server_mac: "02:00:00:00:07:00"
  server_ip: "192.0.2.70"
  agents:
    - name: my-k3s-agent-1
      vmid: 231
      target_node: node1
      mac: "02:00:00:00:07:01"
      ip: "192.0.2.71"
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
  ts_tags: ["tag:example"]
```

The OAuth client secret (`secrets.tailscale.oauth_client_secret`) is passed to the
Tailscale cloud-init module as the node auth key. `ts_tags` must be non-empty, because
Tailscale requires tags for OAuth-generated keys. The OAuth client ID is optional and unused.

The secret keys are read from `secrets.tailscale.*` by default. To use other keys, set
`ts_oauth_client_id_secret` (default `tailscale.oauth_client_id`) and
`ts_oauth_client_secret_secret` (default `tailscale.oauth_client_secret`), for example
`ts_oauth_client_secret_secret: "tailscale.k3s_oauth_client_secret"`. Both control-plane and
worker nodes use the values.

## Directory Layout

```
k3s-cluster/
  blueprint.yaml           # Shared defaults + providers section
  playbooks/
    k3s.yml                # Ansible playbook (OCI variant)
  roles/
    k3s-server/            # Control plane install (OCI variant)
    k3s-agent/             # Worker install (OCI variant)
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

The OCI variant takes an optional `compartment` input (a compartment resource name or an
OCID; default empty). When set, the VCN, subnets and instances use it; when empty they use
`compartment_ocid` from the provider settings.

Shared defaults (`cluster_name`, `k3s_version`, `k3s_server_args`) are at the
top level and apply to both providers.
