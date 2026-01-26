# Kubernetes Provider

The Kubernetes provider manages Kubernetes resources including deployments, services, secrets, RBAC, Helm releases, and custom manifests (CRDs).

## Supported Resources

| Type | Description |
|------|-------------|
| `namespaces` | Kubernetes namespaces |
| `configmaps` | ConfigMaps for configuration data |
| `secrets` | Secrets for sensitive data |
| `persistentvolumeclaims` | PVCs for persistent storage |
| `serviceaccounts` | Service accounts for RBAC |
| `roles` | Namespace-scoped RBAC roles |
| `rolebindings` | Bindings between roles and subjects |
| `clusterroles` | Cluster-scoped RBAC roles |
| `clusterrolebindings` | Cluster-scoped role bindings |
| `deployments` | Deployment workloads |
| `services` | Service resources |
| `ingresses` | Ingress resources |
| `jobs` | One-time job workloads |
| `cronjobs` | Scheduled job workloads |
| `helm_releases` | Helm chart releases |
| `manifests` | Custom Kubernetes manifests (CRDs) |

## Configuration

### Provider Settings

Add kubeconfig path to your environment's `settings.yaml`:

```yaml
name: prod

provider_settings:
  kubernetes:
    kubeconfig_path: "~/.kube/config"
```

The `~` is automatically expanded using Terraform's `pathexpand()` function.

## Resource Reference

### Manifests (Custom Resources)

The `manifests` resource type allows deploying arbitrary Kubernetes manifests, including Custom Resource Definitions (CRDs) installed by operators.

```yaml
resources:
  - provider: kubernetes
    type: manifests
    name: my-custom-resource
    config:
      manifest:
        apiVersion: example.com/v1
        kind: CustomResource
        metadata:
          name: my-resource
          namespace: default
        spec:
          key: value
```

#### Automatic Helm Dependencies

Manifests automatically depend on all Helm releases in the same configuration. This ensures CRDs are installed before resources that use them.

For example, when deploying a Tailscale Connector (CRD) alongside the Tailscale Operator (Helm):

```yaml
resources:
  # Helm release installs the operator and CRDs
  - provider: kubernetes
    type: helm_releases
    name: tailscale-operator
    config:
      chart: tailscale-operator
      repository: https://pkgs.tailscale.com/helmcharts
      namespace: tailscale
      create_namespace: true
      values:
        oauth:
          clientId: "..."
          clientSecret: "..."

  # Manifest uses a CRD defined by the operator
  - provider: kubernetes
    type: manifests
    name: subnet-router
    config:
      manifest:
        apiVersion: tailscale.com/v1alpha1
        kind: Connector
        metadata:
          name: my-subnet-router
        spec:
          hostname: my-router
          subnetRouter:
            advertiseRoutes:
              - 10.0.0.0/16
```

The generated Terraform will include:

```hcl
resource "kubernetes_manifest" "subnet_router" {
  manifest = { ... }

  depends_on = [
    helm_release.tailscale_operator,
  ]
}
```

This ensures the Helm release is applied first, installing the Connector CRD, before Terraform attempts to create the Connector resource.

### Helm Releases

```yaml
resources:
  - provider: kubernetes
    type: helm_releases
    name: nginx-ingress
    config:
      chart: ingress-nginx
      repository: https://kubernetes.github.io/ingress-nginx
      version: "4.8.3"
      namespace: ingress
      create_namespace: true
      values:
        controller:
          replicaCount: 2
```

## Dependencies

Resources are created in dependency order:

```
namespaces → configmaps/secrets/serviceaccounts → deployments → services → ingresses
                                                                    ↓
                                               helm_releases → manifests
```

Manifests depend on both namespaces and helm_releases to ensure CRDs are available.
