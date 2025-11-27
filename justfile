# InfraFoundry - Infrastructure Automation Framework
# Command runner using just (https://just.systems)

# Default recipe to display help
default:
    @just --list

# Display help information
help:
    @echo "InfraFoundry - Infrastructure Automation Framework"
    @echo ""
    @echo "Setup commands:"
    @echo "  just install           Install dependencies with uv"
    @echo "  just dev               Install with dev dependencies"
    @echo "  just clean             Remove build artifacts and caches"
    @echo "  just setup-vscode      Display VS Code extension installation tips"
    @echo "  just install-uv        Install uv package manager"
    @echo "  just install-deps      Install all system dependencies (direnv, age, sops, terraform, ansible)"
    @echo "  just install-direnv    Install direnv"
    @echo "  just install-age       Install age encryption tool"
    @echo "  just install-sops      Install SOPS secrets manager"
    @echo "  just install-terraform Install Terraform"
    @echo "  just install-ansible   Install Ansible via uv"
    @echo ""
    @echo "Development commands:"
    @echo "  just test          Run pytest"
    @echo "  just coverage      Run tests with full coverage report"
    @echo "  just lint          Run ruff linter"
    @echo "  just format        Format code with ruff"
    @echo "  just check         Run all checks (lint + type check)"
    @echo ""
    @echo "Infrastructure commands:"
    @echo "  just plan ENV      Generate and plan infrastructure (dry-run)"
    @echo "  just apply ENV     Apply infrastructure changes"
    @echo "  just destroy ENV   Destroy infrastructure"

# Install dependencies with uv
install:
    uv pip install -e .

# Install with dev dependencies
dev:
    uv pip install -e ".[dev]"

# Remove build artifacts and caches
clean:
    rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache tmp/htmlcov/ tmp/coverage.xml tmp/.coverage tmp/.pytest_cache tmp/.mypy_cache tmp/.ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Run pytest
test:
    pytest -v

# Run tests with full coverage report
coverage:
    pytest --cov=src/infrafoundry --cov-report=term-missing --cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v
    @echo ""
    @echo "Coverage report generated:"
    @echo "  HTML: tmp/htmlcov/index.html"
    @echo "  XML:  tmp/coverage.xml"
    @echo ""
    @echo "Target: 90% coverage (currently ~92%)"

# Run unit tests only
test-unit:
    pytest -v -m unit tests/unit/

# Run integration tests only
test-integration:
    pytest -v -m integration tests/integration/

# Run tests with coverage (alternative)
test-coverage:
    pytest -v --cov=infrafoundry --cov-report=html --cov-report=term-missing
    @echo "Coverage report generated in htmlcov/index.html"

# Run fast tests (skip slow ones)
test-fast:
    pytest -v -m "not slow"

# Run ruff linter
lint:
    ruff check src/ tests/

# Format code with ruff
format:
    ruff format src/ tests/
    ruff check --fix src/ tests/

# Run all checks (lint + type check)
check: lint
    mypy src/

# Generate and plan infrastructure (dry-run)
plan ENV:
    infra plan --env {{ENV}} --dry-run

# Apply infrastructure changes
apply ENV:
    infra apply --env {{ENV}}

# Destroy infrastructure
destroy ENV:
    infra destroy --env {{ENV}}

# Display VS Code extension installation tips
setup-vscode:
    @echo "VS Code Extensions Setup"
    @echo "========================"
    @echo ""
    @echo "When you open this workspace in VS Code, you'll be prompted to install"
    @echo "recommended extensions. Alternatively, you can:"
    @echo ""
    @echo "1. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)"
    @echo "2. Type 'Extensions: Show Recommended Extensions'"
    @echo "3. Click 'Install All' button"
    @echo ""
    @echo "Recommended extensions include:"
    @echo "  • Python development tools (Pylance, debugpy)"
    @echo "  • Code quality (Ruff, Black)"
    @echo "  • Testing (pytest)"
    @echo "  • Infrastructure (Terraform, Ansible)"
    @echo "  • Git tools (GitLens)"
    @echo ""
    @echo "See .vscode/extensions.json for the complete list."

# Install uv package manager
install-uv:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v uv &> /dev/null; then
        echo "✓ uv already installed: $(uv --version)"
        exit 0
    fi
    echo "Installing uv package manager..."
    # Try download with curl first
    if command -v curl &> /dev/null; then
        echo "Downloading with curl..."
        if curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh 2>/dev/null; then
            echo "✓ Downloaded with curl"
            sh /tmp/uv-install.sh
            rm -f /tmp/uv-install.sh
            export PATH="$HOME/.cargo/bin:$PATH"
            echo "✓ uv installed"
            exit 0
        fi
    fi
    # Try download with wget
    if command -v wget &> /dev/null; then
        echo "Downloading with wget..."
        if wget -q https://astral.sh/uv/install.sh -O /tmp/uv-install.sh 2>/dev/null; then
            echo "✓ Downloaded with wget"
            sh /tmp/uv-install.sh
            rm -f /tmp/uv-install.sh
            export PATH="$HOME/.cargo/bin:$PATH"
            echo "✓ uv installed"
            exit 0
        fi
    fi
    # Fall back to pip if available
    if command -v pip &> /dev/null || command -v pip3 &> /dev/null; then
        echo "Installing with pip..."
        if pip install uv 2>/dev/null || pip3 install uv 2>/dev/null; then
            echo "✓ uv installed via pip"
            exit 0
        fi
    fi
    echo "✗ Failed to install uv. Please install manually: https://github.com/astral-sh/uv"
    exit 1

# Install all system dependencies
install-deps: install-direnv install-age install-sops install-terraform install-ansible
    @echo ""
    @echo "✓ All dependencies installed successfully!"

# Install direnv
install-direnv:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v direnv &> /dev/null; then
        echo "✓ direnv already installed: $(direnv --version)"
        exit 0
    fi
    echo "Installing direnv..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y direnv
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install direnv
    else
        echo "Unsupported OS: $OSTYPE"
        exit 1
    fi
    # Configure direnv for bash if not already configured
    if ! grep -q 'direnv hook bash' ~/.bashrc 2>/dev/null; then
        echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
        echo "✓ Added direnv hook to ~/.bashrc"
    fi
    echo "✓ direnv installed"

# Install age encryption tool
install-age:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v age &> /dev/null; then
        echo "✓ age already installed: $(age --version 2>&1 | head -1)"
        exit 0
    fi
    echo "Installing age..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y age
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install age
    else
        echo "Unsupported OS: $OSTYPE"
        exit 1
    fi
    echo "✓ age installed"

# Install SOPS secrets manager
install-sops:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v sops &> /dev/null; then
        echo "✓ SOPS already installed: $(sops --version 2>&1 | head -1)"
        exit 0
    fi
    echo "Installing SOPS..."
    SOPS_VERSION=$(curl -s "https://api.github.com/repos/getsops/sops/releases/latest" | grep '"tag_name":' | sed -E 's/.*"v?([^"]+)".*/\1/')
    echo "Latest version: $SOPS_VERSION"
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        wget -q "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops_${SOPS_VERSION}_amd64.deb" -O /tmp/sops.deb
        sudo dpkg -i /tmp/sops.deb
        rm /tmp/sops.deb
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install sops
    else
        echo "Unsupported OS: $OSTYPE"
        exit 1
    fi
    echo "✓ SOPS $SOPS_VERSION installed"

# Install Terraform
install-terraform:
    #!/usr/bin/env bash
    set -euo pipefail
    TF_VERSION=$(curl -s "https://api.github.com/repos/hashicorp/terraform/releases/latest" | grep '"tag_name":' | sed -E 's/.*"v?([^"]+)".*/\1/')
    if command -v terraform &> /dev/null; then
        CURRENT_TF_VERSION=$(terraform version -json 2>/dev/null | grep -o '"terraform_version":"[^"]*"' | cut -d'"' -f4)
        if [[ "$CURRENT_TF_VERSION" == "$TF_VERSION" ]]; then
            echo "✓ Terraform already up to date: $TF_VERSION"
            exit 0
        fi
        echo "Current version: $CURRENT_TF_VERSION, upgrading to: $TF_VERSION"
    fi
    echo "Installing Terraform $TF_VERSION..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        wget -q "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip" -O /tmp/terraform.zip
        sudo unzip -o /tmp/terraform.zip -d /usr/local/bin/
        sudo chmod +x /usr/local/bin/terraform
        rm /tmp/terraform.zip
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        ARCH=$(uname -m)
        if [[ "$ARCH" == "arm64" ]]; then
            wget -q "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_darwin_arm64.zip" -O /tmp/terraform.zip
        else
            wget -q "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_darwin_amd64.zip" -O /tmp/terraform.zip
        fi
        sudo unzip -o /tmp/terraform.zip -d /usr/local/bin/
        sudo chmod +x /usr/local/bin/terraform
        rm /tmp/terraform.zip
    else
        echo "Unsupported OS: $OSTYPE"
        exit 1
    fi
    echo "✓ Terraform $TF_VERSION installed"

# Install Ansible via uv
install-ansible:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v uv &> /dev/null; then
        echo "⚠ uv not found. Installing uv first..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    if [[ -f "pyproject.toml" ]]; then
        echo "Installing InfraFoundry with Ansible..."
        uv pip install -e .
        echo "✓ Ansible installed via uv"
    else
        echo "Installing Ansible directly..."
        uv pip install ansible
        echo "✓ Ansible installed"
    fi
