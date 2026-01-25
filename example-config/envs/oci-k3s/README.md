# OCI K3s Cluster with Tailscale

K3s Kubernetes cluster on Oracle Cloud Infrastructure (OCI) Always Free Tier with Tailscale overlay network.

## Documentation

Full documentation: **[docs/examples/oci-k3s-cluster.md](../../../docs/examples/oci-k3s-cluster.md)**

Or view online at: https://endavis.github.io/infrafoundry/examples/oci-k3s-cluster/

## Quick Start

1. Update `settings.yaml` with your OCI credentials and Tailscale auth key
2. Update `oci/instances.yaml` with your image OCID and SSH key
3. Encrypt settings: `sops --encrypt --in-place settings.yaml`
4. Deploy: `infra apply --env oci-k3s`

## Files

- `settings.yaml` - OCI credentials, Tailscale auth key
- `oci/network.yaml` - VCN, subnets, gateways
- `oci/instances.yaml` - Control plane + worker instances
- `files/cloud-init-snippets/tailscale.yaml` - Tailscale installation
