# OCI k3s Cluster Example

Thin example consumer of the [`oci-k3s-cluster`](../../../blueprints/oci-k3s-cluster/README.md)
blueprint. Deploys a k3s Kubernetes cluster on OCI ARM Always-Free-Tier
instances with a Tailscale overlay network for management access.

## Structure

```
envs/oci-k3s/
├── settings.yaml                  # OCI credentials, Tailscale secrets
├── k3s-cluster/
│   └── infrafoundry.yml           # Per-tenancy variables (image OCID, SSH key, tailnet)
└── files/
    └── cloud-init-snippets/
        └── tailscale.yaml         # Tailscale install snippet (referenced by blueprint)
```

All deployment logic — VCN, subnets, instances, ansible roles,
post-terraform installer, tailscale cleanup, cluster verification —
lives in `blueprints/oci-k3s-cluster/`. See the [blueprint README](../../../blueprints/oci-k3s-cluster/README.md)
for the full variable reference and design notes.

## Quick start

1. Edit `settings.yaml` with your OCI credentials (tenancy OCID, user OCID,
   API key fingerprint, private key path, region, compartment OCID) and
   Tailscale auth key + API key.
2. Edit `k3s-cluster/infrafoundry.yml` with:
   - Your Ubuntu ARM image OCID for the chosen region
   - Your SSH public key
   - Your Tailscale tailnet DNS suffix
3. Encrypt: `sops --encrypt --in-place envs/oci-k3s/settings.yaml`
4. Plan:  `foundry -c example-config infra plan --env oci-k3s`
5. Apply: `foundry -c example-config infra apply --env oci-k3s`

## Destroy

`foundry -c example-config infra destroy --env oci-k3s` runs the blueprint's
`before_destroy` Tailscale cleanup script automatically, then tears down
the VCN, subnets, and instances.

## Shared roles

The k3s install logic is provided by `example-config/roles/k3s-server/` and
`example-config/roles/k3s-agent/` — the same roles the proxmox k3s variant
uses. They are not duplicated into the blueprint.
