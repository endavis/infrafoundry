# InfraFoundry Documentation Template

Use this template as the baseline for new or refactored docs so content stays consistent across guides. Not every section is mandatory, but keep the order to aid scanability.

## Title

Short, action-oriented name (e.g., “Validation and Pre-Flight Checks”).

## Overview

- 2–3 sentence summary of the topic and why it matters to InfraFoundry users.
- Mention the primary commands, components, or providers involved.

## Audience and Prerequisites

- **Audience:** Who should read this (operators, contributors, etc.).
- **Prereqs:** Environment, access, and tooling required (e.g., `uv`, `terraform`, `ansible`, `sops`, provider creds).

## When to Use This

- Situations or scenarios where this guide applies.
- Call out limitations or cases where another guide is a better fit.

## Quick Start (Happy Path)

1. Concise, ordered steps to accomplish the main task.
2. Use fenced code blocks for commands and YAML/Terraform/Ansible snippets.
3. Keep explanations adjacent to the steps they relate to.

## Configuration Details

- Required and optional fields, with minimal examples.
- File locations and expected structure (e.g., `envs/{env}/resources/*.yaml`).
- Notes on defaults, precedence, and environment variables (`INFRAFOUNDRY_*` and provider-specific envs).

## Validation and Checks

- How to validate configs or runs (e.g., `infra validate --env <env> --check-api --check-refs`).
- Typical outputs and what pass/fail looks like.

## Examples

- Minimal, focused examples that map to real tasks.
- Include both configuration snippets and the commands to use them.

## Related Documentation

- Cross-links to other InfraFoundry docs that expand the topic (e.g., settings, validation, runners, provider guides).
- External references only if essential (API docs, upstream tools).

## Troubleshooting

- Common issues and fixes (symptom → cause → resolution).
- Logs, state paths, or commands to inspect (e.g., `generated/{env}/terraform/{provider}`, `~/.infrafoundry/state.db`).

---

Last updated: YYYY-MM-DD HH:MM TZ


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
