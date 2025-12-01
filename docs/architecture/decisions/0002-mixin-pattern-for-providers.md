# 2. Use Mixin Pattern for Provider Functionality

**Date:** 2025-12-01
**Status:** Accepted

## Context
Infrastructure providers (Proxmox, OPNsense, Kubernetes) share many common behaviors, such as:
- Rendering Jinja2 templates (`.tf` files).
- Grouping resources by type.
- Generating `terraform.tfvars` files.

However, not all providers need all behaviors (e.g., a future API-only provider might not need Terraform generation). A deep inheritance hierarchy (e.g., `BaseProvider -> TerraformProvider -> ProxmoxProvider`) can become rigid and brittle.

## Decision
We will use the **Mixin Pattern** (Composition over Inheritance) to share functionality.

- **`TemplateRendererMixin`**: Setup Jinja2 env and render templates.
- **`ResourceGrouperMixin`**: Organize resources by type.
- **`TerraformGeneratorMixin`**: Handle `.tfvars` generation and file writing.

Providers will inherit from `ProviderBase` and mix in the specific capabilities they need.

## Consequences
**Positive:**
- **Flexibility:** Providers can pick and choose features.
- **Reuse:** Logic is defined once and reused without duplication.
- **Flatter Hierarchy:** Avoids deep inheritance trees.

**Negative:**
- **Complexity:** Can be harder to trace where a method comes from (hidden dependencies).
- **State Management:** Mixins rely on `self` having certain attributes (e.g., `self.template_dir`), requiring careful interface contracts.

## Alternatives Considered
- **Single Base Class with all methods:** Rejected because it violates Interface Segregation Principle (god class).
- **Helper Classes (Composition):** A valid alternative, but Mixins were chosen for Pythonic convenience and to keep the Provider API unified for the Orchestrator.
