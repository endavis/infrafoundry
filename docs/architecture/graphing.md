---
title: "Visualizing Infrastructure Topology"
description: "Render the resource dependency graph as Mermaid with foundry infra analyze graph"
audience:
  - contributors
tags:
  - architecture
---

# Visualizing Infrastructure Topology

## Overview

`foundry infra analyze graph` builds a dependency graph of resources to show creation/destruction order. Output is Mermaid so you can visualize relationships and debug dependencies.

## Audience and Prerequisites

- **Audience:** Operators and reviewers inspecting dependencies before apply/destroy.
- **Prereqs:** Config repo available; `foundry` installed; a target environment with resources.

## When to Use This

- Understanding the dependencies within each provider before applying changes. The graph has no edges between resources of different providers (see [Dependency and Execution Ordering](../configuration/dependency-ordering.md)).
- Reviewing sequencing for complex environments.
- Debugging unexpected ordering or missing references.

## Quick Start

```bash
foundry infra analyze graph --env dev --format mermaid > graph.mmd
```

Render with Mermaid Live Editor or embed in Markdown.

## Configuration Details

- **Command:** `foundry infra analyze graph --env <env> [--format mermaid]`.
- **Nodes:** Provider-scoped resources (e.g., `proxmox:vm-01`, `opnsense:firewall-rule-100`).
- **Edges:** `A --> B` means A depends on B (B created before A; A destroyed before B).
- **Sources of dependencies:** The type-level rules each provider declares in `get_dependencies()`, applied between resources of the same provider only. See [Dependency and Execution Ordering](../configuration/dependency-ordering.md).

## Validation and Checks

- Run `foundry infra doctor --env <env>` to ensure referenced resources exist before graphing.
- Review generated graph to confirm expected ordering; missing edges can signal missing references.

## Examples

- **Mermaid output sample:**
  ```mermaid
  graph TD
      proxmox_vm_web_01["proxmox:vm-web-01"]
      proxmox_network_vlan_10["proxmox:network-vlan-10"]
      proxmox_vm_db_01["proxmox:vm-db-01"]

      proxmox_vm_web_01 --> proxmox_network_vlan_10
      proxmox_vm_db_01 --> proxmox_network_vlan_10
  ```
- **Write Mermaid to a file:**
  ```bash
  foundry infra analyze graph --env prod --format mermaid > graph.mmd
  ```

## Related Documentation

- [InfraFoundry CLI Reference](../usage/cli-reference.md)
- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Orchestrator Architecture](orchestrator-architecture.md)
- [Dependency and Execution Ordering](../configuration/dependency-ordering.md)

## Troubleshooting

- **Symptom:** Missing nodes or edges. **Fix:** Check that the resources exist and that their types are ones the provider declares a dependency for; rerun `foundry infra doctor --env <env>`.
- **Symptom:** Unexpected ordering. **Fix:** Check provider rules and references; verify resource names match between configs.
- **Symptom:** Graph output unreadable. **Fix:** Render the Mermaid output with the Mermaid Live Editor; `mermaid` is the only format.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
