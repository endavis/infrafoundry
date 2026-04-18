# MinIO — Example

Example package consuming the `minio` blueprint. All deployment logic lives in
`blueprints/minio/`; this directory only supplies the per-instance values.

See `blueprints/minio/README.md` for the full variable reference, prerequisites,
and architecture.

## Quick Start

```bash
export KUBECONFIG=~/.kube/<cluster>.yaml

# Deploy operator + tenant
foundry infra apply --env dev --package minio

# Destroy
foundry infra destroy --env dev --package minio
```

## What This Example Demonstrates

- A minimal two-server tenant (`tenant_servers: 2`) with 5Gi volumes, so the
  example fits on a small dev cluster.
- A placeholder `minio_root_password: "CHANGE_ME"` — replace this (typically
  via a SOPS-encrypted `secrets.yaml`) before applying.
- All other variables (operator version, storage class, NodePorts, resource
  limits) inherited from the blueprint defaults.
