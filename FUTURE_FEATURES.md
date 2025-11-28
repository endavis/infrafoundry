# Future Features Roadmap

This document outlines potential value-add features for InfraFoundry to enhance its capabilities as an infrastructure workflow manager.

## 1. Configuration Templating / Blueprints (Completed) ✅
**Goal:** Reduce boilerplate and standardize best practices.
**Description:** A library of reusable "Blueprints" (e.g., "HA Web Cluster", "K8s Cluster") that users can instantiate with minimal parameters.
**Implementation:**
- `infra new --blueprint <name>` command.
- Scaffolding mechanism for config files.
- Internal registry or git-based source for blueprints.

## 2. Visual Topology / Graphing (Completed) ✅
**Goal:** Visualization for documentation and debugging.
**Description:** Generate visual diagrams of the infrastructure graph (dependencies, resources, networks).
**Implementation:**
- Extend `DependencyGraph` to export to Graphviz (DOT) or Mermaid format.
- New `infra graph` command.

## 3. State Locking & Remote Backend Management
**Goal:** Enable safe team collaboration.
**Description:** First-class support for managing Terraform remote backends (S3, GCS, Postgres) and state locking.
**Implementation:**
- Enhance `ConfigManager` to generate backend configurations.
- Support simple backend definition in `settings.yaml`.

## 4. Infrastructure Cost Estimation (FinOps)
**Goal:** Prevent billing shocks and enforce budgets.
**Description:** Predict the cost of a deployment before applying it.
**Implementation:**
- Integrate with tools like Infracost.
- New `CostEstimator` component parsing Terraform plans.
- Policy engine integration for budget caps.

## 5. Automated Drift Remediation
**Goal:** Self-healing infrastructure.
**Description:** Periodic checks for drift with optional auto-remediation.
**Implementation:**
- Daemon mode or cron integration for `infra drift`.
- Configurable auto-apply thresholds.

## 6. Secrets Rotation
**Goal:** Improve security posture.
**Description:** Automated rotation of secrets managed by SOPS.
**Implementation:**
- `infra secrets rotate` command.
- Hooks to update `settings.yaml`, re-encrypt, and redeploy.

## 7. External Vault Integration
**Goal:** Enterprise secret management.
**Description:** Fetch secrets from HashiCorp Vault, AWS Secrets Manager, etc.
**Implementation:**
- Pluggable `SecretProvider` interface (abstracting away SOPS).
