# Visualizing Infrastructure Topology

## Overview

`infra graph` builds a dependency graph of resources to show creation/destruction order. Output is Mermaid (or DOT) so you can visualize relationships and debug dependencies.

## Audience and Prerequisites

- **Audience:** Operators and reviewers inspecting dependencies before apply/destroy.
- **Prereqs:** Config repo available; `uv run infra` installed; a target environment with resources.

## When to Use This

- Understanding cross-provider dependencies before applying changes.
- Reviewing sequencing for complex environments.
- Debugging unexpected ordering or missing references.

## Quick Start

```bash
infra graph --env dev --format mermaid > graph.mmd
```

Render with Mermaid Live Editor or embed in Markdown. Use DOT for alternative tooling (`--format dot`).

## Configuration Details

- **Command:** `infra graph --env <env> [--format mermaid|dot]`.
- **Nodes:** Provider-scoped resources (e.g., `proxmox:vm-01`, `opnsense:firewall-rule-100`).
- **Edges:** `A --> B` means A depends on B (B created before A; A destroyed before B).
- **Sources of dependencies:** Provider rules, cross-resource references, and future explicit `depends_on`.

## Validation and Checks

- Run `infra validate --env <env> --check-refs` to ensure referenced resources exist before graphing.
- Review generated graph to confirm expected ordering; missing edges can signal missing references.

## Examples

- **Mermaid output sample:**
  ```mermaid
  graph TD
      proxmox_vm_web_01["proxmox:vm-web-01"]
      proxmox_network_vlan_10["proxmox:network-vlan-10"]
      opnsense_firewall_web["opnsense:firewall-web"]

      proxmox_vm_web_01 --> proxmox_network_vlan_10
      opnsense_firewall_web --> proxmox_vm_web_01
  ```
- **Generate DOT:**
  ```bash
  infra graph --env prod --format dot > graph.dot
  ```

## Related Documentation

- [InfraFoundry CLI Reference](../usage/cli-reference.md)
- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Orchestrator Architecture](orchestrator-architecture.md)

## Troubleshooting

- **Symptom:** Missing nodes or edges. **Fix:** Ensure resources declare correct references; rerun `infra validate --check-refs`.
- **Symptom:** Unexpected ordering. **Fix:** Check provider rules and references; verify resource names match between configs.
- **Symptom:** Graph output unreadable. **Fix:** Switch format (`--format dot`) and render with DOT tools; simplify by filtering resources before generation (future enhancement).

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
