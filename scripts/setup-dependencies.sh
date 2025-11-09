#!/usr/bin/env bash
#
# InfraFoundry Dependencies Setup
# Installs all required tools: Terraform, Ansible, SOPS, age, direnv

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║     InfraFoundry Dependencies Installation            ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

echo -e "${YELLOW}Detected OS: $OS${NC}"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to get latest version from GitHub
get_latest_version() {
    local repo=$1
    curl -s "https://api.github.com/repos/$repo/releases/latest" | grep '"tag_name":' | sed -E 's/.*"v?([^"]+)".*/\1/'
}

# Install direnv
echo -e "${BLUE}[1/5] Installing direnv...${NC}"
if command_exists direnv; then
    echo -e "${GREEN}✓ direnv already installed: $(direnv --version)${NC}"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update && sudo apt-get install -y direnv
    elif [[ "$OS" == "macos" ]]; then
        brew install direnv
    fi
    echo -e "${GREEN}✓ direnv installed${NC}"
fi

# Configure direnv for bash if not already configured
if ! grep -q 'direnv hook bash' ~/.bashrc 2>/dev/null; then
    echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
    echo -e "${GREEN}✓ Added direnv hook to ~/.bashrc${NC}"
else
    echo -e "${GREEN}✓ direnv already configured in ~/.bashrc${NC}"
fi

# Install age
echo ""
echo -e "${BLUE}[2/5] Installing age (encryption tool)...${NC}"
if command_exists age; then
    echo -e "${GREEN}✓ age already installed: $(age --version 2>&1 | head -1)${NC}"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get install -y age
    elif [[ "$OS" == "macos" ]]; then
        brew install age
    fi
    echo -e "${GREEN}✓ age installed${NC}"
fi

# Install SOPS
echo ""
echo -e "${BLUE}[3/5] Installing SOPS (secrets management)...${NC}"
if command_exists sops; then
    echo -e "${GREEN}✓ SOPS already installed: $(sops --version 2>&1 | head -1)${NC}"
else
    SOPS_VERSION=$(get_latest_version "getsops/sops")
    echo "Installing SOPS version $SOPS_VERSION..."

    if [[ "$OS" == "linux" ]]; then
        wget -q "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops_${SOPS_VERSION}_amd64.deb" -O /tmp/sops.deb
        sudo dpkg -i /tmp/sops.deb
        rm /tmp/sops.deb
    elif [[ "$OS" == "macos" ]]; then
        brew install sops
    fi
    echo -e "${GREEN}✓ SOPS $SOPS_VERSION installed${NC}"
fi

# Install Terraform
echo ""
echo -e "${BLUE}[4/5] Installing Terraform...${NC}"
if command_exists terraform; then
    CURRENT_TF_VERSION=$(terraform version -json 2>/dev/null | grep -o '"terraform_version":"[^"]*"' | cut -d'"' -f4)
    echo "Current Terraform version: $CURRENT_TF_VERSION"
fi

TF_VERSION=$(get_latest_version "hashicorp/terraform")
echo "Latest Terraform version: $TF_VERSION"

if command_exists terraform && [[ "$CURRENT_TF_VERSION" == "$TF_VERSION" ]]; then
    echo -e "${GREEN}✓ Terraform already up to date${NC}"
else
    echo "Installing Terraform $TF_VERSION..."

    if [[ "$OS" == "linux" ]]; then
        wget -q "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip" -O /tmp/terraform.zip
        sudo unzip -o /tmp/terraform.zip -d /usr/local/bin/
        sudo chmod +x /usr/local/bin/terraform
        rm /tmp/terraform.zip
    elif [[ "$OS" == "macos" ]]; then
        wget -q "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_darwin_arm64.zip" -O /tmp/terraform.zip
        sudo unzip -o /tmp/terraform.zip -d /usr/local/bin/
        sudo chmod +x /usr/local/bin/terraform
        rm /tmp/terraform.zip
    fi
    echo -e "${GREEN}✓ Terraform $TF_VERSION installed${NC}"
fi

# Install Ansible (via Python/uv)
echo ""
echo -e "${BLUE}[5/5] Installing Ansible (via uv)...${NC}"
if ! command_exists uv; then
    echo -e "${YELLOW}uv not found. Installing uv first...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install or update InfraFoundry with ansible dependency
if [[ -f "pyproject.toml" ]]; then
    echo "Installing InfraFoundry with Ansible..."
    uv pip install -e .
    echo -e "${GREEN}✓ Ansible installed via uv${NC}"
else
    echo -e "${YELLOW}⚠ Not in InfraFoundry directory, skipping Ansible install${NC}"
fi

# Verify installations
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Installation Summary${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

verify_tool() {
    local tool=$1
    local version_cmd=$2
    if command_exists "$tool"; then
        local version=$($version_cmd 2>&1 | head -1)
        echo -e "${GREEN}✓ $tool: $version${NC}"
    else
        echo -e "${RED}✗ $tool: NOT INSTALLED${NC}"
    fi
}

verify_tool "direnv" "direnv --version"
verify_tool "age" "age --version"
verify_tool "sops" "sops --version"
verify_tool "terraform" "terraform version"
verify_tool "ansible" "ansible --version"

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Next Steps${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "1. Reload your shell or run:"
echo -e "   ${BLUE}source ~/.bashrc${NC}"
echo ""
echo "2. Run the configuration wizard:"
echo -e "   ${BLUE}./scripts/setup-config.sh${NC}"
echo ""
echo "3. Or manually set up your config repo and run:"
echo -e "   ${BLUE}infra secrets init${NC}"
echo -e "   ${BLUE}infra plan --env <your-env>${NC}"
echo ""
