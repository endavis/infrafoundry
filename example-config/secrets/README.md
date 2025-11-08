# Per-Environment Secrets

This directory contains environment-specific encrypted secrets.

## Quick Start

**InfraFoundry automatically loads credentials based on the `--env` flag!** Just create your encrypted secrets and use the CLI:

```bash
# Create and encrypt secrets for each environment
cat > secrets/dev/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox-dev.example.com:8006/api2/json
proxmox_token_id: terraform@pve!dev-token
proxmox_token_secret: dev-secret-here
EOF
sops --encrypt --in-place secrets/dev/proxmox.yaml

# Use with --env flag - credentials load automatically!
infra plan --env dev      # Uses secrets/dev/proxmox.yaml
infra apply --env staging # Uses secrets/staging/proxmox.yaml
infra plan --env prod     # Uses secrets/prod/proxmox.yaml
```

**No manual environment switching required!** ✨

## Structure

```
secrets/
├── age.key                    # Encryption key (git-ignored)
├── .sops.yaml                 # SOPS configuration
├── dev/                       # Development environment
│   ├── proxmox.yaml           # Encrypted Proxmox credentials
│   ├── opnsense.yaml          # Encrypted OPNsense credentials
│   └── kubernetes.yaml        # Encrypted Kubernetes credentials
├── staging/                   # Staging environment
│   ├── proxmox.yaml
│   ├── opnsense.yaml
│   └── kubernetes.yaml
└── prod/                      # Production environment
    ├── proxmox.yaml
    ├── opnsense.yaml
    └── kubernetes.yaml
```

## Automatic Credential Loading

The InfraFoundry CLI automatically loads environment-specific credentials when you use the `--env` flag. You don't need to manually export environment variables or use `direnv reload`.

**How it works:**
1. You run: `infra apply --env prod`
2. CLI looks for: `secrets/prod/proxmox.yaml`, `secrets/prod/opnsense.yaml`, etc.
3. CLI decrypts with SOPS and sets environment variables
4. Command runs with correct credentials

**That's it!** No manual steps needed.

## Setup

See [Per-Environment Credentials Guide](../../docs/per-environment-credentials.md) for complete setup instructions.

### Detailed Setup Steps

1. **Initialize secrets directory:**
   ```bash
   mkdir -p secrets/{dev,staging,prod}
   ```

2. **Generate age key (if not already done):**
   ```bash
   infra secrets init
   ```

3. **Create environment secrets:**
   ```bash
   # Dev credentials
   cat > secrets/dev/proxmox.yaml <<EOF
   proxmox_api_url: https://proxmox-dev.example.com:8006/api2/json
   proxmox_token_id: terraform@pve!dev-token
   proxmox_token_secret: dev-secret-here
   EOF

   # Encrypt
   sops --encrypt --in-place secrets/dev/proxmox.yaml
   ```

4. **Use with InfraFoundry CLI:**
   ```bash
   # Credentials load automatically based on --env flag!
   infra plan --env dev
   infra apply --env staging
   infra destroy --env prod
   ```

## Optional: Manual Credential Loading

For advanced use cases (debugging, testing, CI/CD scripts), you can manually load credentials in `.envrc.local`:

```bash
# Set environment (defaults to dev)
export INFRA_ENV="${INFRA_ENV:-dev}"

# Function to load environment-specific secrets
load_env_secrets() {
    local env=$1
    local secrets_dir="${INFRAFOUNDRY_CONFIG_REPO}/secrets/${env}"

    # Load Proxmox credentials
    if [[ -f "${secrets_dir}/proxmox.yaml" ]]; then
        PROXMOX_DATA=$(sops --decrypt "${secrets_dir}/proxmox.yaml" 2>/dev/null)
        if [[ $? -eq 0 ]]; then
            export PROXMOX_API_URL=$(echo "$PROXMOX_DATA" | yq eval '.proxmox_api_url' -)
            export PROXMOX_API_TOKEN_ID=$(echo "$PROXMOX_DATA" | yq eval '.proxmox_token_id' -)
            export PROXMOX_API_TOKEN_SECRET=$(echo "$PROXMOX_DATA" | yq eval '.proxmox_token_secret' -)
        fi
    fi

    # Load OPNsense credentials
    if [[ -f "${secrets_dir}/opnsense.yaml" ]]; then
        OPNSENSE_DATA=$(sops --decrypt "${secrets_dir}/opnsense.yaml" 2>/dev/null)
        if [[ $? -eq 0 ]]; then
            export OPNSENSE_API_URL=$(echo "$OPNSENSE_DATA" | yq eval '.opnsense_api_url' -)
            export OPNSENSE_API_KEY=$(echo "$OPNSENSE_DATA" | yq eval '.opnsense_api_key' -)
            export OPNSENSE_API_SECRET=$(echo "$OPNSENSE_DATA" | yq eval '.opnsense_api_secret' -)
        fi
    fi
}

# Uncomment to auto-load on direnv reload (not needed for normal CLI usage)
# load_env_secrets "$INFRA_ENV"
# echo "Loaded credentials for environment: $INFRA_ENV"
```

**Note:** Manual loading is **optional** and rarely needed. The CLI automatically loads credentials based on `--env` flag.

## Security Notes

1. **Never commit unencrypted secrets or age keys**
   - `.gitignore` should include `secrets/*.key` and `secrets/**/*.key`

2. **Backup age key securely**
   - Store in password manager
   - Keep offline backup

3. **Use different tokens per environment**
   - Dev: limited permissions, test data
   - Staging: similar to prod permissions
   - Prod: minimal required permissions, audit logging

4. **For production, consider:**
   - Separate age keys per environment (more access control)
   - External secret management (AWS Secrets Manager, Vault)
   - GitHub Secrets for CI/CD

## See Also

- [Per-Environment Credentials Guide](../../docs/per-environment-credentials.md) - Complete setup options
- [State Management](../../docs/state-management.md) - Understanding state types
- [SOPS Documentation](https://github.com/getsops/sops) - Secret encryption
