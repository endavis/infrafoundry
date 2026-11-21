---
title: "Kubernetes Provider"
description: "Manage Kubernetes deployments, services, secrets, RBAC, Helm releases and manifests"
audience:
  - users
tags:
  - providers
---

# Kubernetes Provider

The Kubernetes provider manages Kubernetes resources including deployments, services, secrets, RBAC, Helm releases, and custom manifests (CRDs).

## Supported Resources

| Type | Terraform resource | Description |
|------|--------------------|-------------|
| `namespaces` | `kubernetes_namespace` | Kubernetes namespaces |
| `configmaps` | `kubernetes_config_map` | ConfigMaps for configuration data |
| `secrets` | `kubernetes_secret` | Secrets for sensitive data |
| `persistentvolumeclaims` | `kubernetes_persistent_volume_claim` | PVCs for persistent storage |
| `serviceaccounts` | `kubernetes_service_account` | Service accounts for RBAC |
| `roles` | `kubernetes_role` | Namespace-scoped RBAC roles |
| `rolebindings` | `kubernetes_role_binding` | Bindings between roles and subjects |
| `clusterroles` | `kubernetes_cluster_role` | Cluster-scoped RBAC roles |
| `clusterrolebindings` | `kubernetes_cluster_role_binding` | Cluster-scoped role bindings |
| `deployments` | `kubernetes_deployment` | Deployment workloads |
| `services` | `kubernetes_service` | Service resources |
| `ingresses` | `kubernetes_ingress_v1` | Ingress resources |
| `jobs` | `kubernetes_job` | One-time job workloads |
| `cronjobs` | `kubernetes_cron_job_v1` | Scheduled job workloads |
| `helm_releases` | `helm_release` | Helm chart releases |
| `manifests` | `kubernetes_manifest` | Custom Kubernetes manifests (CRDs) |

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

The `KUBECONFIG` environment variable overrides `kubeconfig_path`: when it is set and not empty, the runner passes it to Terraform as `TF_VAR_kubeconfig_path`. Without either, the generated `variables.tf` defaults to `~/.kube/config`.

`context` (optional) selects a kubeconfig context. It reaches Terraform as `TF_VAR_kubeconfig_context` and becomes `config_context` in the `kubernetes` and `helm` provider blocks, and `infra doctor` uses the same context. Without it Terraform uses the kubeconfig's current context.

The generated Terraform pins the `hashicorp/kubernetes` provider to `~> 2.23`. It adds `hashicorp/helm` (`~> 2.12`) and a `helm` provider block only when the environment has `helm_releases`.

!!! note "Naming rule"
    `namespaces`, `configmaps`, `deployments` and `services` take the object name and the Terraform label from `config.name`. Every other type uses the top-level `name`.

    A `name` that differs from the object name needs the resource-centric format. In the provider-centric format the config is the entry itself, so `config.name` always equals `name`. An explicit `config.name` is never overwritten by the top-level `name`. This lets a Deployment and a Service share one object name, which the Service's default selector relies on:

    ```yaml
    resources:
      - provider: kubernetes
        type: deployments
        name: web
        config:
          name: web
          containers:
            - name: web
              image: nginx:1.27
      - provider: kubernetes
        type: services
        name: web-svc
        config:
          name: web
          ports:
            - port: 80
    ```

    The automatic `depends_on` references use the same label source, so `name` and `config.name` may differ: a namespace with `name: apps-ns` and `config.name: apps` is declared as `kubernetes_namespace.apps`, and the resources that depend on it point at `kubernetes_namespace.apps`.

### Several clusters per environment

One environment can manage several clusters. Each extra cluster is a provider instance, as for [OPNsense firewalls](opnsense.md#several-firewalls-per-environment) ([ADR-0030](../decisions/0030-kubernetes-clusters-are-provider-instances-several-per-environment.md)). Declare them under `clusters:`:

```yaml
provider_settings:
  kubernetes:
    primary: edge
    clusters:
      edge: {kubeconfig_path: ~/.kube/edge.yaml}
      cloud: {kubeconfig_path: ~/.kube/cloud.yaml, context: cloud-admin}
```

| Key | Meaning |
|:----|:--------|
| `clusters` | Map of cluster name to `kubeconfig_path` and `context`. Names use lowercase letters, digits and `-` (1-32 characters). |
| `primary` | The primary cluster. Required with more than one entry. |

There are no shared defaults. Combining `clusters:` with a top-level `kubeconfig_path` or `context` is an error.

**Choosing a cluster for a resource**, most specific first:

1. The entry's own `cluster: <name>`.
2. A file-level `cluster: <name>` beside `resources:` or the provider-centric list key. It stamps the `kubernetes` resources of the file only.
3. The package manifest's `cluster: <name>`. It stamps the package's `kubernetes` resources only, including those a blueprint brings in, even when the package lives under another provider's directory.
4. The primary.

**Ids, files and state.** The primary keeps the id `kubernetes`, `generated/<env>/terraform/kubernetes/` and its state, so converting a flat configuration to `clusters:` changes nothing for it. Every other cluster is `kubernetes@<name>` with its own `terraform/kubernetes@<name>/` directory and state rows. The same resource name may exist on two clusters. Moving a resource between clusters removes it from one and creates it on the other.

**CLI.** `-P kubernetes` selects the primary plus every declared cluster that has resources. `--cluster <name>` (repeatable) on `infra plan|apply|destroy|doctor` selects exact clusters. It cannot be combined with `-p` or `-r`, needs `-P kubernetes` if `-P` is used, and combines with `--firewall`.

**`KUBECONFIG`.** With a flat configuration it still overrides `kubeconfig_path`. Once `clusters:` is declared it is ignored for every cluster, the primary included, and a warning is logged once, so a shell pointing at one cluster cannot redirect another's resources.

## Resource Reference

Each type below lists the keys it reads from `config`, taken from its Terraform template. Keys marked "default" use the value shown when you omit them. Every type also accepts `config.depends_on`, a list of Terraform addresses that is merged after the automatic references (see [Dependencies](#dependencies)). Annotations and labels are string maps.

### Namespaces

`name`, `labels`, `annotations`.

```yaml
resources:
  - provider: kubernetes
    type: namespaces
    name: apps
    config:
      name: apps
      labels:
        team: platform
```

### ConfigMaps

`name`, `namespace` (default `default`), `data` (a map of key to string; required).

### Secrets

`namespace` (default `default`), `labels`, `annotations`, `type` (default `Opaque`), `data`, `string_data`, `data_secrets`, `string_data_secrets`.

`data` values are base64-encoded, as in a Kubernetes Secret manifest, and are rendered to the Terraform provider's `binary_data` argument. A `data` value that is not valid base64 fails validation. `string_data` values are plain strings, rendered to the provider's `data` argument, which encodes them. You may set both; `string_data` wins on a duplicate key.

To take a value from the environment's SOPS `secrets.yaml` instead of writing it in the config, use the `_secrets` maps. Each maps a key to a dotted secret reference:

```yaml
config:
  string_data:
    username: admin
  string_data_secrets:        # rendered into `data`, as plain values
    password: app.admin_token
  data_secrets:               # rendered into `binary_data`; the secret must already be base64
    tls.key: app.tls_key_b64
```

The values reach Terraform as sensitive variables set through `TF_VAR_*` at apply, so they never appear in the generated `.tf` files. A resolved value still lands in the Terraform state, as with any Terraform-managed secret. `data_secrets` values must be base64, like `data`. A key in `string_data` or `string_data_secrets` is left out of `binary_data`. The same key in `string_data` and `string_data_secrets`, or in `data` and `data_secrets`, fails validation.

A reference of the form `package.<key>` takes the value from the `secrets.yaml` of the package that defines the resource, not from the environment's file. `package` is a reserved prefix. It works in `string_data_secrets`, `data_secrets`, `value_secret` and `terraform_secrets`, and resolves from that package only. See [Package Secret References](../configuration/infrastructure-packages.md#package-secret-references).

A reference of the form `outputs.<provider>.<output>` takes the value from another provider's Terraform output instead of SOPS, for example `outputs.tailscale.oauth_client_k8s_operator_secret`:

- It works in `string_data_secrets`, in `terraform_secrets` and in `set_sensitive[*].value_secret` of a Helm release. It is an error in `data_secrets` (an output is not base64), in another provider's `terraform_secrets`, and for the Kubernetes provider's own outputs. A non-primary cluster (`kubernetes@<name>`) may read the primary's `outputs.kubernetes.*`. A non-primary cluster cannot be a producer, because the reference grammar excludes `@` and `-`.
- `outputs` is a reserved prefix, so a top-level SOPS key named `outputs` cannot be referenced. Both parts after it use lowercase letters, digits and `_`.
- The producer is applied first, and destroyed last. On `apply` the value is read with `terraform output -json` from `generated/<env>/terraform/<provider>/`. If the run does not include the producer (for example `-P kubernetes`), the value comes from its existing state. When that directory or the output is missing, apply fails and names the reference; run `infra apply --env <env> -P <provider>` first.
- On `plan`, `destroy` and `validate` a missing output gets a placeholder value and a warning, so the preview of a first apply still works. The placeholder never reaches an apply.
- The value is held in memory for the Terraform call, and is never logged or written to the generated files. It lands in this provider's Terraform state, as with any Terraform-managed secret.

!!! note "Existing `string_data` secrets"
    Earlier versions wrapped `string_data` values in `base64encode()`, so the stored value was base64 text. The next apply updates such a secret in place to the plain string you wrote. A consumer that decoded the value twice to work around this must be updated.

!!! note "Existing `data` secrets"
    Earlier versions passed `data` values to the provider's `data` argument unchanged, which encodes them, so a base64 value was stored still base64-encoded. `data` now takes base64 and stores the decoded bytes. A secret that held plain text in `data` fails validation; move those values to `string_data`. A secret that held base64 text changes its stored value to the decoded content on the next apply, so a consumer that decoded it a second time must be updated.

### PersistentVolumeClaims

- Metadata: `namespace` (default `default`), `labels`, `annotations`.
- Spec: `access_modes` (default `[ReadWriteOnce]`), `storage` (default `1Gi`), `limits.storage`, `storage_class_name`, `volume_name`.
- Selector: `selector.match_labels`, and `selector.match_expressions` as a list of `key`, `operator` and `values`.
- `wait_until_bound`.

### Service accounts, roles and bindings

All of these share `labels` and `annotations`, and use the top-level `name`.

| Type | Keys |
|------|------|
| `serviceaccounts` | `namespace` (default `default`), `image_pull_secrets` (a list of `name`), `automount_service_account_token` |
| `roles` | `namespace` (default `default`), `rules` |
| `rolebindings` | `namespace` (default `default`), `role_ref.kind` (default `Role`), `role_ref.name`, `subjects` |
| `clusterroles` | `rules`, `aggregation_rule.cluster_role_selectors` (a list of `match_labels`) |
| `clusterrolebindings` | `role_ref.name` (the kind is always `ClusterRole`), `subjects` |

A rule in `roles` has `api_groups`, `resources`, `verbs` and optional `resource_names`. A rule in `clusterroles` also accepts `non_resource_urls`. A subject has `kind`, `name` and optional `namespace` and `api_group`.

```yaml
resources:
  - provider: kubernetes
    type: serviceaccounts
    name: reader
    config:
      namespace: apps
  - provider: kubernetes
    type: roles
    name: pod-reader
    config:
      namespace: apps
      rules:
        - api_groups: [""]
          resources: ["pods"]
          verbs: ["get", "list", "watch"]
  - provider: kubernetes
    type: rolebindings
    name: reader-binds-pod-reader
    config:
      namespace: apps
      role_ref:
        name: pod-reader
      subjects:
        - kind: ServiceAccount
          name: reader
          namespace: apps
```

### Deployments

`name`, `namespace` (default `default`), `labels`, `replicas` (default `1`), `strategy`, `containers` and `volumes`.

A container has `name`, `image`, `command`, `args`, `ports` (a list of `containerPort`, `name`, `protocol`), `env`, `volume_mounts` and `resources.limits` and `resources.requests` (string maps). `env`, `volume_mounts` and the pod `volumes` take the same shape as in [Jobs and CronJobs](#jobs-and-cronjobs): an `env` entry sets `value` or `value_from` (`secret_key_ref` or `config_map_key_ref`), and a volume is a `config_map` (with optional `items`), `secret`, `persistent_volume_claim` or `empty_dir`.

`strategy.type` is `RollingUpdate` or `Recreate`. Use `Recreate` for a single replica that mounts a `ReadWriteOnce` volume, so the old pod releases it first.

The pod selector is always `app: <config.name>`, and the pod template carries that label plus your `labels`.

### Services

`name`, `namespace` (default `default`), `labels`, `type` (default `ClusterIP`), `selector` and `ports`.

`selector` is the value of the `app` label to select, a plain string that defaults to `config.name`. A port has `port`, `targetPort` (default: `port`), `protocol`, `name` and `nodePort` (written only when `type` is `NodePort`).

### Ingresses

`namespace` (default `default`), `labels`, `annotations`, `ingress_class_name`, `default_backend`, `tls` and `rules`.

- `default_backend.service` has `name` and `port.number` or `port.name`.
- A `tls` entry has `hosts` and `secret_name`.
- A rule has `host` and `paths`. A path has `path`, `path_type` (default `Prefix`) and `backend.service` with `name` and `port.number` or `port.name`.

### Jobs and CronJobs

!!! note "Changing the namespace replaces the object"
    A job or cronjob that sets `config.namespace` to something other than `default` is created in that namespace. For an existing one, the next apply replaces it, because `metadata.namespace` cannot change in place.

`jobs`: `namespace` (default `default`), `labels`, `annotations`, `backoff_limit`, `completions`, `parallelism`, `active_deadline_seconds`, `ttl_seconds_after_finished`, `restart_policy` (default `Never`), `service_account_name`, `containers`, `volumes` and `wait_for_completion`.

`cronjobs`: `namespace` (default `default`), `labels`, `annotations`, `schedule`, `timezone`, `concurrency_policy`, `suspend`, `starting_deadline_seconds`, `successful_jobs_history_limit`, `failed_jobs_history_limit`, `backoff_limit`, `ttl_seconds_after_finished`, `restart_policy` (default `OnFailure`), `service_account_name`, `containers` and `volumes`.

Containers in both types have `name`, `image`, `command`, `args`, `env`, `resources` and `volume_mounts`.

- An `env` entry has `name` and either `value` or `value_from` with `secret_key_ref` or `config_map_key_ref` (each with `name` and `key`).
- A `volume_mounts` entry has `name`, `mount_path`, `read_only` and `sub_path`.
- A volume has `name` and one of `config_map` (`name`; for jobs also `items`), `secret.secret_name`, `persistent_volume_claim.claim_name` or `empty_dir`.

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

Only `apiVersion`, `kind`, `metadata.name`, `metadata.namespace`, `metadata.labels`, `metadata.annotations` and `spec` of the manifest are rendered; any other top-level key of the manifest is dropped. `foundry infra doctor` checks that the CRD group of each custom `apiVersion` (read from `manifest.apiVersion`) is installed in the cluster. A missing group is a warning when the configuration also defines Helm releases, which may install the CRD.

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
              - 198.51.100.0/24
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

The keys `config` reads:

`chart`, `repository`, `version`, `namespace` (default `default`), `create_namespace`, `timeout`, `max_history`, `values` (a mapping rendered as YAML), `set` (a list of `name`, `value`, `type`) and `set_sensitive` (a list of `name` and either `value` or `value_secret`, a dotted reference into the environment's SOPS secrets, injected through `TF_VAR_*` like the secret `_secrets` maps).

The booleans are `atomic`, `cleanup_on_fail`, `dependency_update`, `force_update`, `lint`, `recreate_pods`, `replace`, `reset_values`, `reuse_values`, `skip_crds`, `wait` and `wait_for_jobs`.

`repository` is required only when `chart` is a bare chart name; `oci://` references and chart paths need none. `foundry infra plan`, `apply` and `doctor` report a Helm release that has no `chart`, or a bare chart name with no `repository`.

### Validation

`infra plan` and `infra apply` run the offline checks (cross-references, secret `data` encoding, `terraform_secrets` references including unresolved refs and base64 of `data_secrets` values, Helm releases). `infra doctor` adds the cluster checks. It finds the kubeconfig in the same order as Terraform: `KUBECONFIG`, then `kubeconfig_path`, then `~/.kube/config`. The cluster checks authenticate with a bearer `token`, a `tokenFile` or a client certificate (`client-certificate-data` / `client-key-data`, or the file path forms). A missing kubeconfig gives a warning, not an error, because the cluster may be created in the same apply.

For `deployments` only, the offline checks report an error when a `volume_mounts` entry names a volume that `volumes` does not declare, when an `env` entry sets both or neither of `value` and `value_from`, or when `strategy.type` is not `RollingUpdate` or `Recreate`.

## Dependencies

Resources are created in dependency order:

```
namespaces → configmaps/secrets/serviceaccounts/persistentvolumeclaims → deployments → services → ingresses
                                                                    ↓
                                               helm_releases → manifests
```

The provider automatically generates Terraform `depends_on` blocks for all resource types based on this dependency graph. For example, a `secrets` resource will include `depends_on` referencing the namespace resources it depends on, ensuring Terraform creates namespaces before secrets.

Manifests depend on both namespaces and helm_releases to ensure CRDs are available.

The automatic references cover every resource of each depended-on type in the run, not only the ones in the same namespace (`KubernetesProvider._build_dependency_refs`). A type adds references only when at least one resource of that type is present. See [Dependency and Execution Ordering](../configuration/dependency-ordering.md) for how this fits the other ordering levels.

Resources can also declare explicit `depends_on` in their configuration, which are merged with the auto-generated dependencies:

```yaml
resources:
  - provider: kubernetes
    type: deployments
    name: my-app
    config:
      name: my-app
      namespace: default
      depends_on:
        - kubernetes_config_map.extra_config
```

## Common Use Cases

All names and hosts below are placeholders.

### A web application

A namespace, a configuration map, a secret, a deployment, a service and an ingress. Each of `namespaces`, `configmaps`, `deployments` and `services` repeats its name in `config.name` (see the naming rule above).

```yaml
resources:
  - provider: kubernetes
    type: namespaces
    name: web
    config:
      name: web
  - provider: kubernetes
    type: configmaps
    name: web-config
    config:
      name: web-config
      namespace: web
      data:
        LOG_LEVEL: info
  - provider: kubernetes
    type: secrets
    name: web-credentials
    config:
      namespace: web
      data:
        API_TOKEN: example-token
  - provider: kubernetes
    type: deployments
    name: web
    config:
      name: web
      namespace: web
      replicas: 2
      containers:
        - name: web
          image: registry.example.com/web:1.0.0
          ports:
            - containerPort: 8080
  - provider: kubernetes
    type: services
    name: web
    config:
      name: web
      namespace: web
      ports:
        - port: 80
          targetPort: 8080
  - provider: kubernetes
    type: ingresses
    name: web
    config:
      namespace: web
      ingress_class_name: nginx
      rules:
        - host: app.example.com
          paths:
            - path: /
              backend:
                service:
                  name: web
                  port:
                    number: 80
```

### A service account with a role and binding

See the example under [Service accounts, roles and bindings](#service-accounts-roles-and-bindings).

### A scheduled job with a persistent volume

The cronjob and the claim both land in the `default` namespace because neither sets `namespace`.

```yaml
resources:
  - provider: kubernetes
    type: persistentvolumeclaims
    name: backup-data
    config:
      storage: 5Gi
  - provider: kubernetes
    type: cronjobs
    name: nightly-backup
    config:
      schedule: "0 2 * * *"
      containers:
        - name: backup
          image: registry.example.com/backup:1.0.0
          volume_mounts:
            - name: data
              mount_path: /data
      volumes:
        - name: data
          persistent_volume_claim:
            claim_name: backup-data
```

### A Helm operator and a custom resource

See [Automatic Helm Dependencies](#automatic-helm-dependencies) for a Helm release and a manifest that uses the CRD it installs.

## Ansible Playbook Generation

`KubernetesProvider.generate_ansible` writes two files to `generated/<env>/ansible/kubernetes/`:

- `playbook.yml` runs on `localhost`. For each `deployments` resource it runs `kubectl wait --for=condition=available --timeout=300s` and then `kubectl get deployments -o wide`, and shows the registered output with `debug`. With no deployments there are no tasks.
- `inventory.yml` holds `localhost` with `ansible_connection: local` and the variable `kubeconfig` (default `~/.kube/config`).

!!! warning "`infra plan` and `infra apply` do not generate or run these files"
    The orchestrator calls `generate_<tool>` and runs a runner only when the runner's `is_iac_runner` property is true. `AnsibleRunner` inherits `BaseRunner.is_iac_runner = False`, so `foundry infra plan` and `foundry infra apply` neither write the playbook nor run it. See [Orchestrator Architecture](../architecture/orchestrator-architecture.md) and [Ansible Runner Guide](../runners/ansible.md).
