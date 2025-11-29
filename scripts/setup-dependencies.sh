#!/usr/bin/env bash
#
# InfraFoundry Dependencies Setup
# Installs uv, then uses pydoit to install all required tools

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install uv if needed
echo -e "${BLUE}[1/2] Checking uv package manager...${NC}"
if command_exists uv; then
    echo -e "${GREEN}✓ uv already installed: $(uv --version)${NC}"
else
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo -e "${GREEN}✓ uv installed${NC}"
fi

echo ""
echo -e "${BLUE}[2/2] Installing infrastructure dependencies...${NC}"
echo -e "${YELLOW}Syncing python environment...${NC}"
uv pip install -e ".[dev]"

echo ""
echo -e "${YELLOW}Running: doit install_deps${NC}"
uv run doit install_deps

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

verify_tool "uv" "uv --version"
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
echo -e "   ${BLUE}doit plan --env <your-env>${NC}"
echo ""
echo -e "${GREEN}💡 VS Code Users:${NC}"
echo "   Open this project in VS Code and install recommended extensions:"
echo -e "   ${BLUE}doit setup_vscode${NC} for more details"
echo ""
echo -e "${GREEN}💡 Available Commands:${NC}"
echo -e "   Run ${BLUE}doit list${NC} to see all available commands"