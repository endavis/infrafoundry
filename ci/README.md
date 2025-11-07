# CI/CD Integration Scripts

This directory contains scripts and configurations for integrating InfraFoundry into CI/CD pipelines.

## GitHub Actions

See `.github/workflows/` for example workflows.

## GitLab CI

See `.gitlab-ci.yml.example` for GitLab CI/CD configuration.

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
