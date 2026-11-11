---
title: "Dependency and Execution Ordering"
description: "How InfraFoundry orders providers and resources, which ordering you control, and what is not ordered across providers"
audience:
  - users
tags:
  - configuration
  - providers
---

# Dependency and Execution Ordering

InfraFoundry orders work at several levels. This page lists each level, says what you control at it, and states plainly what the code does not do.

## Overview

| Level | What is ordered | Your control |
|-------|-----------------|--------------|
| [Provider order](#provider-order) | Whole providers, one after another | `provider_order` in `settings.yaml` |
| [Within a provider](#within-a-provider) | Resource types of one provider | Fixed by the provider; Kubernetes also accepts `depends_on` |
| [Cross-provider](#cross-provider-dependencies) | Individual resources across providers | None: no edges are built |

## Audience and Prerequisites

- **Audience:** Operators running more than one provider in an environment.
- **Prerequisites:** An environment with a `settings.yaml` (see [Settings File Structure](settings-file-structure.md)).

## When to Use This

- Deciding whether a firewall change should run before the virtual machines that sit behind it.
- Finding out why a resource was created before another.
- Diagnosing a circular dependency.

## Provider Order

Providers run one after another, in the order given by `provider_order` in the environment's `settings.yaml`. Without it, the order is the planner's default:

```text
opnsense, proxmox, oci, kubernetes
```

A provider that is not in the list runs after all the listed ones. `esxi` and `tailscale` are not in the default list, so they run last unless you name them. For destroy the order is reversed, so the unlisted providers go first and `opnsense` goes last.

```yaml
name: prod

providers:
  - opnsense
  - proxmox
  - kubernetes
  - tailscale

provider_order:
  - opnsense
  - proxmox
  - kubernetes
  - tailscale
```

The sorting is done by `ExecutionPlanner.sort_providers`; the orchestrator builds the planner from the environment in `Orchestrator._create_execution_planner` and applies it in `Orchestrator._iter_provider_batches`.

## Within a Provider

Each provider declares which of its resource types depend on which (`get_dependencies()`). The orchestrator uses these rules to build a dependency graph (`Orchestrator.build_dependency_graph`): a resource depends on every other resource of the **same provider** whose type its type requires.

| Provider | Type-level rules |
|----------|------------------|
| `kubernetes` | `configmaps`, `secrets`, `persistentvolumeclaims`, `serviceaccounts`, `roles` need `namespaces`; `rolebindings` need `namespaces`, `roles`, `serviceaccounts`; `deployments` need `namespaces`, `configmaps`, `secrets`, `serviceaccounts`, `persistentvolumeclaims`; `services` need `namespaces`, `deployments`; `ingresses` need `namespaces`, `services`; `manifests` need `namespaces`, `helm_releases` |
| `proxmox` | `vm` needs `template`, `network`, `storage`, `sdn_vnet`; `container` needs `network`, `storage`, `sdn_vnet`; `sdn_vnet` needs `sdn_zone` |
| `opnsense` | for example `firewall.rules` need `firewall.aliases`, `interfaces.vlans`, `interfaces.assignments`, `routing.gateways`; `interfaces.assignments` need `interfaces.vlans`; Kea reservations need their subnets |
| `oci` | `instance` needs `vcn`, `subnet`; `subnet` needs `vcn` |
| `esxi` | `vm` and `ovf_deployment` need `vswitch`, `portgroup`; `portgroup` needs `vswitch` |
| `tailscale` | `tailnet_key`, `device_tags`, `device_subnet_routes` need `acl` |

How a provider turns these rules into an order differs:

- **Kubernetes** emits Terraform `depends_on` references between the resources (see [Kubernetes Provider](../providers/kubernetes.md#dependencies)).
- **Proxmox and Tailscale** templates carry their own `depends_on` lines, for example the Tailscale auth key on the ACL (`proxmox/templates/proxmox/sdn.tf.j2`, `tailscale/templates/tailscale/tailnet_key.tf.j2`).
- **OPNsense** applies types in the order of its dispatch table and deletes in a separate reverse phase (see [OPNsense Provider](../providers/opnsense.md#apply-order-and-deletes)).

### `depends_on`

`depends_on` is a Kubernetes feature, read from a resource's `config` by the Kubernetes templates, and it takes a list of Terraform addresses. It is not a generic resource field: `ResourceConfig` (`core/provider.py`) has no such field, so putting `depends_on` at the top level of a resource of another provider does nothing.

```yaml
resources:
  - provider: kubernetes
    type: deployments
    name: my-app
    config:
      name: my-app
      depends_on:
        - kubernetes_config_map.extra_config
```

## Cross-Provider Dependencies

There is no ordering between individual resources of different providers at run time. `build_dependency_graph` only adds edges between resources of the same provider, so the graph has no edge from, say, a Kubernetes resource to a Proxmox virtual machine. The only cross-provider ordering is the provider order above, which orders whole providers.

The help text of `-P` on `infra plan`, `infra apply` and `infra destroy` says that cross-provider dependencies pointing at filtered-out providers are skipped for the run. That is accurate but moot, because such edges are never created.

`-P <provider>` limits a run to the named providers. A name that no provider with resources in the environment has is refused with `Unknown provider(s): <names>. Available: <names>`. The flag is mutually exclusive with `-p` and `-r`.

## Inspecting Dependencies

```bash
# the whole graph, as a list or as a Mermaid diagram
foundry infra analyze dependencies --env <env>
foundry infra analyze dependencies --env <env> --format mermaid

# one resource, given as provider:name
foundry infra analyze dependencies --env <env> -r kubernetes:my-app

# what depends on a resource, and the risk of changing it
foundry infra analyze impact --env <env> -r my-app

# a Mermaid graph (the only format `analyze graph` offers)
foundry infra analyze graph --env <env> -f mermaid
```

Graph nodes are named `provider:name`. A cycle among resources is reported as a circular dependency, [IF-DEPENDENCY-001](../reference/errors.md#if-dependency-001-circular-dependency-detected), and the message names the nodes of the cycle.

## Related Documentation

- [Dependency Graphing](../architecture/graphing.md)
- [Settings File Structure](settings-file-structure.md)
- [Kubernetes Provider](../providers/kubernetes.md)
- [OPNsense Provider](../providers/opnsense.md)
- [Lifecycle Hooks](lifecycle-hooks.md)

## Troubleshooting

- **A provider ran earlier than expected.** Check `provider_order`. A provider you did not list runs last, and a destroy runs the order in reverse.
- **`Unknown provider(s)` with `-P`.** The name must match a provider that has resources in the environment; the message lists the available names.
- **Circular dependency.** See [IF-DEPENDENCY-001](../reference/errors.md#if-dependency-001-circular-dependency-detected) and [Troubleshooting Common Errors](../guides/troubleshooting.md).
