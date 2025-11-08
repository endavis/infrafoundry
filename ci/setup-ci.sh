#!/bin/bash
# CI/CD setup script - Run this before infrastructure deployment in CI/CD

set -e

echo "🔧 Setting up InfraFoundry for CI/CD..."

# Check required tools
command -v terraform >/dev/null 2>&1 || { echo "❌ Terraform not found"; exit 1; }
command -v sops >/dev/null 2>&1 || { echo "❌ SOPS not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 not found"; exit 1; }

# Check for uv, install if missing
if ! command -v uv >/dev/null 2>&1; then
    echo "⚠️  uv not found, installing..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    elif command -v pip >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1; then
        pip install uv 2>/dev/null || pip3 install uv
    else
        echo "❌ Cannot install uv (no curl or pip available)"
        exit 1
    fi

    # Verify uv is now available
    if ! command -v uv >/dev/null 2>&1; then
        echo "❌ Failed to install uv"
        exit 1
    fi
    echo "✅ uv installed"
fi

echo "✅ Required tools found"

# Check environment variables
if [ -z "$SOPS_AGE_KEY_FILE" ]; then
    echo "⚠️  SOPS_AGE_KEY_FILE not set"

    # Check if SOPS_AGE_KEY is set (CI/CD secret)
    if [ -n "$SOPS_AGE_KEY" ]; then
        echo "📝 Creating age key from SOPS_AGE_KEY environment variable..."
        mkdir -p secrets
        echo "$SOPS_AGE_KEY" | base64 -d > secrets/age.key
        chmod 600 secrets/age.key
        export SOPS_AGE_KEY_FILE="$(pwd)/secrets/age.key"
        echo "✅ Age key configured"
    else
        echo "❌ Neither SOPS_AGE_KEY_FILE nor SOPS_AGE_KEY is set"
        exit 1
    fi
fi

# Verify age key exists
if [ ! -f "$SOPS_AGE_KEY_FILE" ]; then
    echo "❌ Age key file not found: $SOPS_AGE_KEY_FILE"
    exit 1
fi

echo "✅ Age key verified: $SOPS_AGE_KEY_FILE"

# Set defaults for InfraFoundry
export INFRAFOUNDRY_CONFIG_REPO="${INFRAFOUNDRY_CONFIG_REPO:-envs}"
export INFRAFOUNDRY_SECRETS_DIR="${INFRAFOUNDRY_SECRETS_DIR:-secrets}"
export INFRAFOUNDRY_LOG_LEVEL="${INFRAFOUNDRY_LOG_LEVEL:-INFO}"

echo "✅ InfraFoundry configuration:"
echo "   - Config repo: $INFRAFOUNDRY_CONFIG_REPO"
echo "   - Secrets dir: $INFRAFOUNDRY_SECRETS_DIR"
echo "   - Log level: $INFRAFOUNDRY_LOG_LEVEL"

# Check environment argument
if [ -z "$1" ]; then
    echo "❌ Usage: $0 <environment>"
    echo "   Example: $0 dev"
    exit 1
fi

ENVIRONMENT=$1
echo "🎯 Target environment: $ENVIRONMENT"

# Validate environment exists (check in config repo path)
ENV_PATH="$INFRAFOUNDRY_CONFIG_REPO/$ENVIRONMENT"
if [ ! -d "$ENV_PATH" ]; then
    echo "❌ Environment directory not found: $ENV_PATH"
    exit 1
fi

echo "✅ Environment validated"

# Install Python dependencies if needed
if [ ! -f ".venv/bin/activate" ] && [ ! -f "venv/bin/activate" ]; then
    echo "📦 Installing Python dependencies with uv..."
    uv pip install -e .
    echo "✅ Dependencies installed"
fi

echo "✅ CI/CD setup complete!"
echo ""
echo "🚀 Ready to deploy. Run:"
echo "   infra plan --env $ENVIRONMENT"
echo "   infra apply --env $ENVIRONMENT --auto-approve"
