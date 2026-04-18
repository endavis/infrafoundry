# MinIO Distributed Object Storage Blueprint

Reusable blueprint that deploys the [MinIO](https://min.io/) Operator and a
distributed MinIO tenant on an existing k3s (or other Kubernetes) cluster. All
resources are managed declaratively via the InfraFoundry Kubernetes provider
(Helm releases, namespace, credentials secret, NodePort Service manifest) — no
shell scripts.

Companion to the `k3s-cluster` blueprint: deploy k3s first, then layer MinIO
on top. See `blueprints/aiqum/README.md` for a structural reference.

## Usage

A package consumes this blueprint with a thin manifest that supplies only the
per-instance values:

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: minio
description: "MinIO distributed object storage on k3s cluster"
provider: proxmox
blueprint: minio

variables:
  tenant_name: homelab
  tenant_servers: 4
  tenant_volume_size: "25Gi"
  # minio_root_password — supply via secrets.yaml (SOPS-encrypted)
```

Then:

```bash
export KUBECONFIG=~/.kube/<cluster>.yaml
infra apply --env <env> --package minio
```

## Variables

### Required (must be set in the consuming package)

| Variable | Description | Example |
|---|---|---|
| `tenant_name` | Tenant identifier; becomes the tenant Helm release name and is templated into all tenant-scoped resource names | `homelab` |
| `minio_root_password` | MinIO root password (store in SOPS-encrypted `secrets.yaml`) | (secret) |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `operator_namespace` | `minio-operator` | Namespace for the MinIO Operator |
| `operator_chart_version` | `6.0.4` | MinIO Operator/Tenant Helm chart version |
| `tenant_namespace` | `minio-tenant` | Namespace for the tenant resources |
| `tenant_servers` | `4` | Servers in pool-0 (distributed mode requires >= 4) |
| `tenant_volumes_per_server` | `1` | Volumes per server |
| `tenant_volume_size` | `25Gi` | PersistentVolume size per server |
| `tenant_storage_class` | `local-path` | StorageClass for tenant PVCs |
| `minio_root_user` | `minioadmin` | MinIO root username |
| `minio_cpu_request` | `250m` | CPU request per pod |
| `minio_memory_request` | `512Mi` | Memory request per pod |
| `minio_cpu_limit` | `1` | CPU limit per pod |
| `minio_memory_limit` | `2Gi` | Memory limit per pod |
| `api_node_port` | `30900` | NodePort for the S3 API (port 9000) |
| `console_node_port` | `30909` | NodePort for the web console (port 9090) |

## Prerequisites

- A Kubernetes cluster is already up and all nodes are `Ready` (for homelab, see
  the `k3s-cluster` blueprint).
- `KUBECONFIG` is exported for the target cluster.
- All target nodes are labeled with `minio=true`:
  ```bash
  kubectl label node --all minio=true
  ```
- The `tenant_storage_class` (default `local-path`) is installed on the cluster.

## Architecture

This blueprint creates five Kubernetes resources:

| Resource | Type | Name | Description |
|---|---|---|---|
| Operator Helm release | `helm_releases` | `minio-operator` | MinIO Operator (CRDs + controller) |
| Tenant namespace | `namespaces` | `{tenant_name}-ns` | Namespace for tenant resources |
| Credentials secret | `secrets` | `{tenant_name}-env-configuration` | Holds `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` |
| Tenant Helm release | `helm_releases` | `{tenant_name}` | MinIO tenant (pool config, resources, node selector) |
| NodePort Service | `manifests` | `{tenant_name}-external` | Exposes API (9000) and console (9090) on the node IPs |

The tenant Helm release depends on both the operator (for the CRDs) and the
credentials secret (referenced via `tenant.configuration.name` and
`tenant.configSecret.name` with `existingSecret=true`).

### Design notes

- **Distributed mode with erasure coding**: 4 servers x 1 drive each
  (MinIO uses EC:2, surviving up to 2 drive/node failures for reads, 1 for
  writes). Increase `tenant_servers` for larger clusters.
- **Local-path storage by default**: Each MinIO pod gets a PersistentVolume on
  the node's local filesystem. Override `tenant_storage_class` to use a
  different provisioner (e.g. `longhorn`, `rook-ceph-block`).
- **No TLS**: `tenant.certificate.requestAutoCert=false`. Add a TLS ingress
  in front if needed.
- **NodePort exposure**: The operator creates a ClusterIP Service; this
  blueprint adds a second NodePort Service for direct external access without
  an ingress controller.

## Access and Credentials

Once applied:

- **S3 API**: `http://<any-node-ip>:<api_node_port>` (default `30900`)
- **Console**: `http://<any-node-ip>:<console_node_port>` (default `30909`)
- **Username**: value of `minio_root_user` (default `minioadmin`)
- **Password**: value of `minio_root_password` (from SOPS-encrypted
  `secrets.yaml` in the consuming package)

The Helm tenant chart is configured with `configSecret.existingSecret=true`,
so it reads the credentials from the Terraform-managed secret instead of
creating its own. `accessKey`/`secretKey` are blanked out to avoid chart
validation errors.

## Multi-instance usage

All tenant-scoped resource names are templated on `tenant_name`, so multiple
tenants can coexist on the same cluster:

```yaml
# minio-a package
variables:
  tenant_name: team-a
  tenant_namespace: minio-team-a
  api_node_port: 30910
  console_node_port: 30919

# minio-b package
variables:
  tenant_name: team-b
  tenant_namespace: minio-team-b
  api_node_port: 30920
  console_node_port: 30929
```

The `minio-operator` Helm release is cluster-global and shared across tenants;
it is intentionally kept as a literal name.
