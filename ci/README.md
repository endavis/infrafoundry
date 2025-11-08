# CI/CD Integration Scripts

This directory contains scripts and configurations for integrating InfraFoundry into CI/CD pipelines.

## Overview

InfraFoundry includes comprehensive CI/CD workflows for both **testing** and **infrastructure deployment**.

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
   - Runs 286 unit tests with coverage
   - Enforces 69% coverage threshold
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
   - Black formatting
   - Ruff linting
   - isort import sorting
   - mypy type checking

**Local Testing:**
```bash
make test          # Run all tests
make coverage      # Full coverage report
make lint          # Run linting
make format        # Format code
```

**See [docs/ci-cd-testing.md](../docs/ci-cd-testing.md) for complete testing guide.**

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

See `.gitlab-ci.yml.example` for GitLab CI/CD configuration.

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
- `INFRAFOUNDRY_CONFIG_REPO` - Path to configuration repository (default: `envs`)
- `INFRAFOUNDRY_SECRETS_DIR` - Secrets directory (default: `secrets`)
- `INFRAFOUNDRY_LOG_LEVEL` - Logging level (default: `INFO`)

**Example:**
```bash
# Set required secrets
export SOPS_AGE_KEY=$(cat secrets/age.key | base64 -w 0)

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

## Environment Variables for CI/CD

Required environment variables for CI/CD:
- `SOPS_AGE_KEY`: Base64-encoded age key for decrypting secrets
- `INFRAFOUNDRY_ENV`: Environment to deploy (dev, staging, prod)
- Provider-specific credentials (PROXMOX_*, OPNSENSE_*, etc.)

## Best Practices

1. **Secrets**: Never commit unencrypted secrets. Use SOPS with age encryption.
2. **State**: Use remote state backends (S3, Terraform Cloud) for production.
3. **Auto-approve**: Use `--auto-approve` flag in CI/CD for apply/destroy.
4. **Validation**: Always run `plan` before `apply` in CI/CD pipelines.
5. **Notifications**: Integrate with Slack/Teams for deployment notifications.
