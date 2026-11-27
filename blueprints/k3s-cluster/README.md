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
The `k3s-dns` role (see [Cluster DNS](#cluster-dns)) is a third, standalone role.

#### Login user

The OCI nodes are reached as `ansible`, like the Proxmox variant. A fresh image only has
`ubuntu`, so the `k3s-bootstrap` role (`playbooks/k3s-bootstrap.yml`) connects as `ubuntu` and
creates `ansible` with the package's `ssh_public_key` and passwordless sudo. It never touches
k3s. It runs in two places:

- On create, `k3s-post-terraform.sh` waits for SSH as `ubuntu`, runs the bootstrap, waits for
  SSH as `ansible`, then runs `k3s.yml` as `ansible`.
- On every apply, the `k3s-bootstrap` after_apply handler (`scripts/oci/k3s-bootstrap.sh`)
  runs first, so existing clusters get the user before `k3s-dns` and `verify-cluster` log in
  as `ansible`. A failure is a warning (`continue_on_error`) and is retried on the next apply.

#### Node kubeconfig mode

The node kubeconfig (the k3s `k3s.yaml` file) is owner-only (`0600`). New clusters get this
from the install step. On every apply, the `k3s-kubeconfig-mode` after_apply handler
(`scripts/oci/k3s-kubeconfig-mode.sh`, `playbooks/k3s-kubeconfig-mode.yml`) brings existing OCI
clusters in line: it sets `write-kubeconfig-mode: "0600"` in the k3s `config.yaml` and
the file's mode on the control node. It restarts nothing and runs after `k3s-bootstrap`. A
failure is a warning (`continue_on_error`) and is retried on the next apply.

On Proxmox, the same-named handler (`scripts/proxmox/k3s-kubeconfig-mode.sh`) does this for
clusters installed before the install step set the mode. It reaches the server node as `ansible`,
directly or through the package's `jumphost`, and pipes `k3s-kubeconfig-mode-node.sh` to it as
root. That script sets the `config.yaml` line, rewrites a `--write-kubeconfig-mode` flag in the
k3s systemd unit to `600` and runs `systemctl daemon-reload` (command-line flags override
`config.yaml`), and runs `chmod 600` on `k3s.yaml`. It restarts nothing, and a failure is a
warning that is retried on the next apply.

| Variant | Login user |
| :--- | :--- |
| Proxmox | `ansible` (cloud-init) |
| OCI | `ansible` (created by `k3s-bootstrap`; `ubuntu` only for the bootstrap) |

#### Cluster DNS

**Cause.** The kubelet builds each pod's `resolv.conf` from the node's own. On a Tailscale node
that is `100.100.100.100` plus the tailnet search domains, which musl-based pods (Alpine) cannot
use for external names.

**Fix.** The `k3s-dns` role gives k3s its own resolver file and points the kubelet at it:

- `/etc/rancher/k3s/resolv.conf` with the configured nameservers and search domains.
- a k3s config drop-in, `50-infrafoundry-dns.yaml` in `/etc/rancher/k3s/config.yaml.d`, with
  `resolv-conf: <that file>`.

It restarts `k3s` or `k3s-agent` only when one of the files changed, then restarts the CoreDNS
deployment only if something changed. It never installs or uninstalls k3s, and never touches
`/var/lib/rancher`. It runs in two places: imported at the end of `playbooks/k3s.yml` on create,
and from the `k3s-dns` after_apply handler (`scripts/oci/k3s-dns.sh`, `playbooks/k3s-dns.yml`
only) on every later apply, so existing clusters are fixed on their next apply.

**Inputs.**

| Input | Default | Meaning |
| :--- | :--- | :--- |
| `k3s_dns_nameservers` | `["169.254.169.254"]` | 1 to 3 resolvers (the OCI VCN resolver); `[]` turns the step off |
| `k3s_dns_search` | `[]` | Cluster-wide search domains; `[]` derives `<vcn_dns_label>.oraclevcn.com` |

The search list is one cluster-wide list because the kubelet passes it into every pod.

**Limits.**

- If the CoreDNS restart fails, run `kubectl -n kube-system rollout restart deployment/coredns`.
- The after_apply handler runs on the operator host, not the jumphost, and does not fail the
  apply (`continue_on_error`). On a jumphost setup the create-time import does the work.
- Pods no longer resolve `*.ts.net` names, since the Tailscale resolver is out of the path.
- The Proxmox variant is not wired: it installs k3s with an SSH script, not these roles, and
  has no known platform resolver. The role is provider-neutral, so it can be wired in later.

#### Tailscale SSH

The post-terraform script reaches the nodes over Tailscale SSH. The tailnet policy's `ssh`
rules must allow the controller's tag to SSH to the nodes' tags (for example `tag:controller`
to `tag:k3s-node`) and must allow both `ubuntu` (the bootstrap) and `ansible`. When upgrading an
existing cluster, add `ansible` to the rule before re-applying. Without such a rule the script stops at once with
"tailnet policy does not permit you to SSH to this node" instead of waiting.

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

#### SSH host keys (Proxmox and OCI)

The Proxmox and OCI post-apply scripts check each node against a pinned SSH host key
(`StrictHostKeyChecking=yes`), not the first key the node presents. InfraFoundry generates
one key pair per node, cloud-init installs it, and the public keys reach the scripts as
`ssh_known_hosts`.

- Run `foundry secrets host-keys --env <env>` before the first apply, and once after
  upgrading to a version that pins host keys. `infra plan` fails until it has run.
- New nodes get a generated key. Nodes that already exist are pinned: the key they present
  now is recorded and the nodes are not changed.
- A node pinned while it already existed has only its public key recorded, so before rebuilding
  it, destroy it, run `foundry secrets host-keys --env <env> --regenerate <node-name>`, then
  apply. `infra plan` and `infra apply` stop before creating it otherwise. A node whose key was
  generated keeps that key across a rebuild.
- `Host key verification failed` from a script or from Ansible means a node does not present
  the recorded key, for example after a rebuild without `--regenerate`.
- On OCI the nodes are reached over Tailscale SSH, which presents the node's `/etc/ssh`
  ed25519 key, so the same key pair is installed through an extra cloud-config part of the
  Tailscale module. Existing nodes are pinned by scanning `<node>.<tailnet>`; run the command
  from a host on the tailnet. Ansible runs with `ANSIBLE_HOST_KEY_CHECKING=True` against the
  pinned file.

See [Infrastructure Packages: SSH Host Keys](../../docs/configuration/infrastructure-packages.md#ssh-host-keys)
and [ADR-0032](../../docs/decisions/0032-blueprint-vms-get-pre-generated-ssh-host-keys-that-scripts-pin.md).

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
    k3s-dns.yml            # Cluster DNS only (OCI variant, also run after apply)
    k3s-bootstrap.yml      # Creates the ansible login user (OCI variant, also run after apply)
    k3s-kubeconfig-mode.yml  # Owner-only node kubeconfig (OCI variant, also run after apply)
  roles/
    k3s-server/            # Control plane install (OCI variant)
    k3s-agent/             # Worker install (OCI variant)
    k3s-dns/               # Cluster DNS isolation (OCI variant)
    k3s-bootstrap/         # ansible login user (OCI variant)
    k3s-kubeconfig-mode/   # owner-only node kubeconfig (OCI variant)
  providers/
    proxmox/
      vm.yaml              # Proxmox VM resource template (each VM tagged with its IP)
      dhcp.yaml            # OPNsense DHCP reservation template
    oci/
      instance.yaml        # OCI compute instance template
      network.yaml         # OCI VCN + subnet template
  scripts/
    proxmox/
      k3s-post-terraform.sh
      k3s-kubeconfig-mode.sh  # after_apply: owner-only node kubeconfig
      k3s-kubeconfig-mode-node.sh  # piped to the server node as root
      k3s-lib.sh           # shared ssh helpers, sourced
    oci/
      k3s-post-terraform.sh
      k3s-bootstrap.sh     # after_apply: create the ansible login user
      k3s-kubeconfig-mode.sh  # after_apply: owner-only node kubeconfig
      k3s-dns.sh           # after_apply: cluster DNS only
      k3s-lib.sh           # shared helpers, sourced
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
