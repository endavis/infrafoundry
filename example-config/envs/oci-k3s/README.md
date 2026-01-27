# OCI K3s Cluster with Tailscale

K3s Kubernetes cluster on Oracle Cloud Infrastructure (OCI) Always Free Tier with Tailscale overlay network.

## Documentation

- **Full Guide:** [docs/examples/oci-k3s-cluster.md](../../../docs/examples/oci-k3s-cluster.md)
- **Design Decisions:** [DECISIONS.md](./DECISIONS.md) - Explains all architectural choices
- **Online Docs:** https://endavis.github.io/infrafoundry/examples/oci-k3s-cluster/

## Quick Start

1. Update `settings.yaml` with your OCI credentials and Tailscale auth key
2. Update `oci/instances.yaml` with your image OCID and SSH key
3. Encrypt settings: `sops --encrypt --in-place settings.yaml`
4. Deploy: `infra apply --env oci-k3s`

## Destroy Workflow

```bash
# 1. Clean up Tailscale devices first
TAILSCALE_API_KEY=tskey-api-xxx ./scripts/cleanup-tailscale.sh

# 2. Destroy infrastructure
infra destroy --env oci-k3s
```

## Files

| File | Purpose |
|------|---------|
| `settings.yaml` | OCI credentials, Tailscale auth key |
| `DECISIONS.md` | Design decisions and reasoning |
| `oci/network.yaml` | VCN, subnets, gateways |
| `oci/instances.yaml` | Control plane + worker instances |
| `files/cloud-init-snippets/tailscale.yaml` | Bootstrap: DNS, Tailscale |
| `scripts/cleanup-tailscale.sh` | Pre-destroy Tailscale cleanup |

## Key Design Decision: OCI Firewall Fix

OCI Ubuntu instances block K3s networking by default. The fix is applied via Ansible AFTER K3s installation (not cloud-init). See [DECISIONS.md](./DECISIONS.md) for details.
