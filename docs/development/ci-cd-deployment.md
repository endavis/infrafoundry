# CI/CD Infrastructure Deployment Guide

## Overview

InfraFoundry includes comprehensive CI/CD workflows for infrastructure deployment. This guide covers setting up automated infrastructure deployment pipelines.

For test automation and code quality CI, see [CI/CD Testing Guide](ci-cd-testing.md).

---

## Test Automation (GitHub Actions)

**Workflow:** `.github/workflows/tests.yml`

**Purpose:** Automated testing, coverage reporting, and code quality checks

**Triggers:**
- Push to `main`, `dev`, or `develop` branches
- Pull requests to `main` or `dev`
- Manual workflow dispatch

**Jobs:**

1. **Main Test Suite**
   - Runs comprehensive unit tests with coverage
   - Enforces coverage threshold
   - Uploads coverage to Codecov
   - Comments coverage on PRs
   - Generates HTML/XML reports

2. **Python Matrix**
   - Tests on Python 3.12 (minimum)
   - Tests on Python 3.13 (latest)

3. **Integration Tests**
   - Installs Terraform and Ansible
   - Tests external tool integration

4. **Code Quality**
   - Ruff formatting (format and check)
   - Ruff linting
   - mypy type checking

**Local Testing:**
```bash
doit test          # Run all tests
doit coverage      # Full coverage report
doit lint          # Run linting
doit format        # Format code
```

---

## Infrastructure Deployment (GitHub Actions)

**Workflow:** `.github/workflows/infra-deploy.yml`

**Purpose:** Automated infrastructure deployment

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main`
- Manual workflow dispatch

**Example Usage:**
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/setup-ci.sh dev
      - run: infra apply --env dev --auto-approve
```

---

## GitLab CI

See [GitLab CI Example](../examples/GITLAB_CI_EXAMPLE.md) for GitLab CI/CD configuration.

---

## Setup Script: `setup-ci.sh`

**Purpose:** Prepare CI/CD environment for infrastructure deployment

**Usage:**
```bash
./ci/setup-ci.sh <environment>
```

**What it does:**
1. Validates required tools (Terraform, SOPS, Python, uv)
2. Installs uv if missing
3. Decodes `SOPS_AGE_KEY` from environment variable
4. Creates age key file for secret decryption
5. Sets InfraFoundry environment variables
6. Validates target environment exists
7. Installs Python dependencies

**Required Environment Variables:**
- `SOPS_AGE_KEY` - Base64-encoded age encryption key
- `SOPS_AGE_KEY_FILE` - Path to age key (alternative to SOPS_AGE_KEY)

**Optional Environment Variables:**
- `INFRAFOUNDRY_CONFIG_REPO` - Path to configuration repository (required if not using --config-dir)
- `INFRAFOUNDRY_LOG_LEVEL` - Logging level (default: `INFO`)

**Example:**
```bash
# Set required secrets
export SOPS_AGE_KEY=$(cat envs/dev/age.key | base64 -w 0)

# Run setup
./ci/setup-ci.sh dev

# Deploy infrastructure
infra apply --env dev --auto-approve
```

---

## Environment Variables for CI/CD

### Required for Testing

- `CODECOV_TOKEN` (optional) - Codecov API token for coverage upload

### Required for Deployment

**Secrets:**
- `SOPS_AGE_KEY` - Base64-encoded age key for decrypting secrets

**Infrastructure:**
- `INFRAFOUNDRY_CONFIG_REPO` - Path to configuration repository (if separate)
- `INFRAFOUNDRY_ENV` - Target environment (dev, staging, prod)

**Provider Credentials:**
- `PROXMOX_API_URL` - Proxmox API endpoint
- `PROXMOX_API_TOKEN_ID` - Proxmox token ID
- `PROXMOX_API_TOKEN_SECRET` - Proxmox token secret
- `OPNSENSE_API_URL` - OPNsense API endpoint
- `OPNSENSE_API_KEY` - OPNsense API key
- `OPNSENSE_API_SECRET` - OPNsense API secret
- `KUBECONFIG` (optional) - Kubernetes configuration

---

## Best Practices

1. **Secrets**: Never commit unencrypted secrets. Use SOPS with age encryption.
2. **State**: Use remote state backends (S3, Terraform Cloud) for production.
3. **Auto-approve**: Use `--auto-approve` flag in CI/CD for apply/destroy.
4. **Validation**: Always run `plan` before `apply` in CI/CD pipelines.
5. **Notifications**: Integrate with Slack/Teams for deployment notifications.

## Related Documentation

- [CI/CD Testing Guide](ci-cd-testing.md)
- [Separate Config Repo CI/CD](../guides/ci-cd-with-separate-config-repo.md)
- [Age Key Management](../guides/age-key-management.md)

---

Last updated: 2026-01-25

---
[Back to Table of Contents](../index.md)
