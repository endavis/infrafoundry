# OCI k3s Cluster Blueprint

Reusable blueprint that deploys a k3s Kubernetes cluster on Oracle Cloud
Infrastructure (OCI) ARM Always-Free-Tier instances with a Tailscale overlay
network for management access: one control plane plus an arbitrary number of
worker nodes. Creates a VCN, two subnets (public for control, private for
workers), and the compute instances, then runs a scripted on_create event
handler that invokes the shared `k3s-server` / `k3s-agent` ansible roles to
install k3s, apply the required iptables fixes, verify the cluster, and write
a local kubeconfig.

The blueprint is the OCI counterpart to `proxmox-k3s-cluster`. Both blueprints
share the same `k3s-server` / `k3s-agent` ansible roles (shipped in the config
repo at `roles/`); only the provider layer and the post-terraform wrapper
differ.

## What's in this blueprint

Follows the same Jinja-loop-over-a-list pattern introduced by
`proxmox-k3s-cluster`: the consumer supplies a `workers:` list of dicts and
`instances.yaml` iterates it with `{% for worker in workers %}`. `workers: []`
is valid and produces a control-only cluster.

The on_create wrapper (`scripts/k3s-post-terraform.sh`) builds an Ansible
inventory on the fly from `INFRAFOUNDRY_PACKAGE_VARS` (via `jq`) and invokes
`ansible-playbook` against the blueprint's `playbook.yml`. This keeps the
blueprint agnostic to worker count without relying on a statically generated
inventory file.

## Usage

A package consumes this blueprint with a thin manifest that supplies the
per-tenancy values:

```yaml
# envs/<env>/<package>/infrafoundry.yml
name: k3s-cluster
description: "OCI k3s cluster"
blueprint: oci-k3s-cluster
provider: oci

variables:
  cluster_name: my-k3s
  control_name: my-k3s-control

  # Required: Ubuntu ARM image OCID for your region
  image: "ocid1.image.oc1.iad.aaaaaaa..."

  # Required: SSH public key for the ubuntu user
  ssh_public_key: "ssh-rsa AAAA... user@host"

  # Required for worker access: Tailscale tailnet DNS suffix
  tailnet: "tail-abcde.ts.net"

  # Worker list inherited from blueprint defaults (2 workers).
  # Override to add/remove workers:
  # workers:
  #   - name: my-k3s-worker-0
  #     ocpus: 1
  #     memory_gb: 8
```

Then:

```bash
foundry infra apply --env <env>
```

## Variables

### Required (must be set in the consuming package)

| Variable | Description | Example |
|---|---|---|
| `image` | Ubuntu ARM image OCID for the target OCI region | `ocid1.image.oc1.iad.aaaaaaa...` |
| `ssh_public_key` | SSH public key for the `ubuntu` user | `ssh-rsa AAAA...` |
| `tailnet` | Tailscale tailnet DNS suffix (needed to reach private workers) | `tail-abcde.ts.net` |

### Secrets (required from `settings.yaml`)

The consumer environment's `settings.yaml` must supply:

- `secrets.tailscale.auth_key` — Tailscale reusable auth key (used by the
  `tailscale` cloud-init snippet to join each node to the tailnet)
- `secrets.tailscale.api_key` — Tailscale API token (used by the
  `before_destroy` cleanup script)

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `cluster_name` | `k3s-cluster` | Logical cluster name; used in the kubeconfig filename |
| `control_name` | `k3s-control` | Control plane hostname |
| `instance_shape` | `VM.Standard.A1.Flex` | OCI compute shape |
| `control_ocpus` | `2` | OCPUs on the control plane |
| `control_memory_gb` | `8` | RAM (GiB) on the control plane |
| `control_boot_volume_gb` | `50` | Boot volume size (GiB) on the control plane |
| `worker_boot_volume_gb` | `50` | Boot volume size (GiB) on each worker |
| `workers` | 2 workers (1 OCPU / 8 GiB each) | Worker node list — see schema below |
| `vcn_name` | `k3s-vcn` | VCN display name |
| `vcn_cidr` | `10.0.0.0/16` | VCN CIDR |
| `vcn_dns_label` | `k3svcn` | VCN DNS label |
| `control_subnet_name` | `k3s-control-subnet` | Public subnet name |
| `control_subnet_cidr` | `10.0.0.0/24` | Public subnet CIDR |
| `control_subnet_dns_label` | `ctrl` | Public subnet DNS label |
| `worker_subnet_name` | `k3s-worker-subnet` | Private subnet name |
| `worker_subnet_cidr` | `10.0.1.0/24` | Private subnet CIDR |
| `worker_subnet_dns_label` | `work` | Private subnet DNS label |
| `tailnet` | `""` | Tailnet DNS suffix; empty falls back to bare hostnames (only workable for the control plane) |
| `k3s_version` | `""` (latest) | Pinned k3s version for the installer |
| `k3s_server_args` | `""` | Extra k3s server installer flags |
| `k3s_oci_firewall_fix` | `true` | Apply the OCI iptables fix after k3s installation (see Design Notes) |
| `kubeconfig_local_path` | `~/.kube/{{ cluster_name }}.yaml` | Local destination for the fetched kubeconfig |

### Worker dict schema

Each entry in the `workers:` list must be a mapping:

| Field | Description | Example |
|---|---|---|
| `name` | Worker hostname | `k3s-worker-0` |
| `ocpus` | OCPUs (ARM A1 = whole cores) | `1` |
| `memory_gb` | RAM in GiB | `8` |

The default (2 workers at 1 OCPU / 8 GiB each, plus a 2-OCPU control plane)
maxes the ARM Always-Free-Tier budget (4 OCPUs, 24 GB RAM). Shrink or expand
as needed. An empty list (`workers: []`) produces a control-only cluster.

## Cloud-init snippet

This blueprint references a cloud-init snippet named `tailscale`. The
framework resolves snippets from the consuming environment's
`files/cloud-init-snippets/` directory (not from the blueprint), so the
consuming environment must provide `files/cloud-init-snippets/tailscale.yaml`.
A working reference copy is shipped with the example at
`example-config/envs/oci-k3s/files/cloud-init-snippets/tailscale.yaml`.

## Prerequisites

- OCI tenancy with an ARM (A1.Flex) compute quota
- An Ubuntu ARM image OCID for the target region
- A Tailscale tailnet and an auth key (reusable, ephemeral recommended)
- `ansible-playbook`, `jq`, and `bash 4+` on the InfraFoundry host
- The shared `k3s-server` and `k3s-agent` roles under
  `${INFRAFOUNDRY_CONFIG_DIR}/roles`

## Automation Flow

```
foundry infra apply --env <env>
  |
  +-- Terraform: create VCN, subnets, gateways
  +-- Terraform: create control instance (public subnet) + N workers (private subnet)
  +-- Cloud-init on each node: install Tailscale, join tailnet
  |
  +-- on_create (resource: <control_name>):
       |
       +-- k3s-post-terraform.sh
            |
            +-- Build inventory from INFRAFOUNDRY_PACKAGE_VARS via jq
            +-- Wait for SSH reachability on every host (via tailnet FQDN)
            +-- ansible-playbook -> k3s-server role on control
            +-- ansible-playbook -> k3s-agent role on each worker
            +-- Fetch kubeconfig, save locally
  |
  +-- after_apply: verify-cluster.sh (kubectl get nodes; continue_on_error)
```

`before_destroy` runs `scripts/cleanup-tailscale-devices.sh` to purge stale
Tailscale devices for the cluster before `terraform destroy` tears down the
instances.

## Design Notes

The sections below document the architectural decisions made when this
recipe was first built. They explain real lessons learned (especially the
iptables-via-ansible discovery) that should outlive any specific
implementation.

### Network Architecture

**Control plane in a public subnet (10.0.0.0/24), workers in a private
subnet (10.0.1.0/24).** The control plane needs a public IP for the initial
Tailscale registration via cloud-init. Workers use the NAT gateway for
outbound traffic (image pulls, updates) but have no public IP, reducing
attack surface. All management access flows through the Tailscale overlay.

**Alternatives considered:** all-public (exposes workers unnecessarily),
all-private (requires a bastion for initial Tailscale bootstrap).

**Tailscale for management access.** Works across NAT and firewalls, built-in
SSH via `--ssh`, ACL-based access control. Avoids exposing port 22 or the
Kubernetes API (6443) to the internet. Bastion hosts and classic VPNs were
considered and rejected as more complex.

### Firewall / iptables Configuration

**iptables rules are applied by Ansible AFTER k3s installation, NOT in
cloud-init.** This is the most important lesson from the original OCI build.

**The problem:** We originally added the iptables rules in cloud-init
`bootcmd`. They persisted correctly to `/etc/iptables/rules.v4`, but after
k3s installation the live UDP 8472 (VXLAN) rule disappeared, breaking pod-to-
pod networking. TCP 6443 and 10250 rules survived; only UDP 8472 was
removed. Reproducible across multiple destroy/create cycles.

**Root cause:** k3s/flannel specifically manages UDP 8472 and removes
external rules during initialization. The persisted rules file stayed
correct, but the live iptables was clobbered.

**The fix:** apply iptables rules in the `k3s-server` and `k3s-agent` ansible
roles AFTER k3s has finished all its own iptables manipulation. The rules
are then applied last and persist.

**Required rules (source = VCN CIDR):**

| Port | Proto | Purpose |
|------|-------|---------|
| 8472 | UDP | Flannel VXLAN overlay |
| 10250 | TCP | Kubelet API (kubectl logs/exec) |
| 6443 | TCP | Kubernetes API server |

The `k3s_oci_firewall_fix` blueprint variable (default `true`) toggles this
behavior in the shared roles.

**The REJECT rule in FORWARD chain:** OCI Ubuntu images ship with
`REJECT --reject-with icmp-host-prohibited` at the end of the FORWARD
chain, positioned before k3s's FLANNEL-FWD rules. The roles remove it so
pod-to-pod traffic can be processed by FLANNEL-FWD. OCI security lists still
provide the network-level protection.

### Cloud-Init vs Ansible Split

- **Cloud-init** handles first-boot bootstrap: SSH host keys, DNS fallback,
  IPv4 apt pinning, Tailscale install + `tailscale up --ssh`.
- **Ansible** handles everything after: k3s install, iptables fix, kubeconfig
  fetch, cluster verification. Ansible can coordinate between nodes (e.g.
  fetch the k3s join token from the control plane and hand it to workers)
  and retry cleanly on failure.

**Tailscale install uses direct .deb download (not the apt repo).** OCI
first-boot networking is flaky enough that multi-step apt repo setup fails
unpredictably. Fetching the .deb directly with retry logic is more robust.

### Tailscale Integration

- **Reusable + ephemeral auth keys.** One key provisions N nodes; ephemeral
  keys auto-clean stale devices when instances are destroyed.
- **`--ssh` enabled on tailnet join.** Eliminates SSH key distribution; the
  wrapper script and ansible use Tailscale identity for auth.
- **Optional: Tailscale Kubernetes Operator.** Post-deploy workload that
  exposes cluster services directly to the tailnet. Not in scope for this
  blueprint, but documented for reference.

### Destroy Workflow

The `before_destroy` event runs `cleanup-tailscale-devices.sh` to remove
cluster devices from the Tailscale admin console before the OCI instances
are torn down. Without this, stale devices accumulate over successive
create/destroy cycles.

## Notes

- The on_create handler's `requires:` field lists only the control plane
  instance. All worker instances are created in the same terraform apply,
  so the handler fires once after apply completes regardless of worker
  count (matches `proxmox-k3s-cluster`).
- The post-deploy script reads `INFRAFOUNDRY_PACKAGE_VARS` via `jq` to
  iterate the `workers:` list and build the ansible inventory on the fly.
  This pattern lets a bash script handle variable cardinality without
  templating the script itself.
- The blueprint is provider-agnostic at the k3s layer (shared roles), but
  provider-specific at the infrastructure layer (OCI VCN/subnet/instance).
  Any future provider-agnostic "k3s cluster" abstraction (#507) should
  build on top of these two concrete variants.
