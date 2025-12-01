# Example: GitLab CI

## Overview

This example shows a GitLab CI pipeline configuration for running InfraFoundry lint/tests and deployments.

## Audience and Prerequisites

- **Audience:** CI maintainers deploying with InfraFoundry on GitLab.
- **Prereqs:** GitLab CI runners with required tools (Terraform, Ansible, uv/pytest/ruff), and access to config repo/credentials via CI variables.

## When to Use This

- Setting up pipelines for validation, testing, and optional apply/destroy stages.
- Adapting InfraFoundry workflows to GitLab.

## Quick Start

1. Copy the example to `.gitlab-ci.yml` and adjust paths/variables.
2. Set CI variables for provider credentials and `INFRAFOUNDRY_CONFIG_REPO`.

## Configuration Details

- **Stages:** validate/test/apply/destroy (adjust as needed).
- **Variables:** Provide config repo path, provider credentials, and any backend settings via GitLab CI variables.
- **Tools:** Install Terraform/Ansible as part of the job or use pre-baked runner images.

## Validation and Checks

- Ensure `infra validate --env <env>` runs before apply.
- Include coverage/lint jobs similar to GitHub Actions if desired.

## Examples

- **Pipeline skeleton (from example):**
  ```yaml
  stages:
    - validate
    - apply

  validate:
    stage: validate
    script:
      - uv run infra validate --env dev --check-api --check-refs

  apply:
    stage: apply
    script:
      - uv run infra apply --env dev --auto-approve
    when: manual
  ```

## Related Documentation

- [CI/CD Testing Guide](../development/ci-cd-testing.md)
- [Configuration Guide](../configuration.md)
- [Validation and Pre-Flight Checks](../validation.md)

## Troubleshooting

- **Symptom:** Missing tools on runner. **Fix:** Install Terraform/Ansible/uv in the job or use an image that includes them.
- **Symptom:** Config repo not found. **Fix:** Set `INFRAFOUNDRY_CONFIG_REPO` or mount the repo path in CI.
- **Symptom:** Secrets missing. **Fix:** Add CI variables/secrets for provider credentials and SOPS keys; avoid committing secrets.

---

Last updated: 2025-11-29 14:27 GMT
