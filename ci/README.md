# CI/CD Integration Scripts

This directory contains scripts for CI/CD infrastructure deployment.

**Full documentation:** [docs/development/ci-cd-deployment.md](../docs/development/ci-cd-deployment.md)

## Quick Reference

### Setup Script

```bash
./ci/setup-ci.sh <environment>
```

Prepares CI/CD environment for infrastructure deployment:
- Validates required tools (Terraform, SOPS, Python, uv)
- Decodes SOPS_AGE_KEY from environment variable
- Sets InfraFoundry environment variables
- Installs Python dependencies

### Required Environment Variables

- `SOPS_AGE_KEY` - Base64-encoded age encryption key
- `INFRAFOUNDRY_CONFIG_REPO` - Path to configuration repository

### Related Documentation

- [CI/CD Deployment Guide](../docs/development/ci-cd-deployment.md)
- [CI/CD Testing Guide](../docs/development/ci-cd-testing.md)
- [CI/CD with Separate Config Repo](../docs/guides/ci-cd-with-separate-config-repo.md)
