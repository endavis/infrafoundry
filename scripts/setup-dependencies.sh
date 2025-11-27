#!/usr/bin/env bash
#
# InfraFoundry Dependencies Setup
# Installs just command runner, then uses it to install all required tools

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

# Install just command runner
echo -e "${BLUE}[1/2] Installing just command runner...${NC}"
if command_exists just; then
    echo -e "${GREEN}✓ just already installed: $(just --version)${NC}"
else
    echo "Installing just..."
    if [[ "$OS" == "linux" ]]; then
        # Download prebuilt binary for Linux
        JUST_VERSION=$(curl -s "https://api.github.com/repos/casey/just/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        echo "Latest version: $JUST_VERSION"
        wget -q "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-x86_64-unknown-linux-musl.tar.gz" -O /tmp/just.tar.gz
        tar -xzf /tmp/just.tar.gz -C /tmp
        sudo mv /tmp/just /usr/local/bin/
        sudo chmod +x /usr/local/bin/just
        rm /tmp/just.tar.gz
    elif [[ "$OS" == "macos" ]]; then
        # Use homebrew on macOS
        if command_exists brew; then
            brew install just
        else
            echo -e "${RED}Error: Homebrew not found. Please install Homebrew first:${NC}"
            echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    fi
    echo -e "${GREEN}✓ just installed${NC}"
fi
echo ""

# Install all dependencies using just
echo -e "${BLUE}[2/2] Installing infrastructure dependencies...${NC}"
echo -e "${YELLOW}Running: just install-deps${NC}"
echo ""

# Run just install-deps which will install: direnv, age, sops, terraform, ansible
just install-deps

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

verify_tool "just" "just --version"
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
echo -e "${GREEN}💡 VS Code Users:${NC}"
echo "   Open this project in VS Code and install recommended extensions:"
echo -e "   ${BLUE}just setup-vscode${NC} for more details"
echo ""
echo -e "${GREEN}💡 Available Commands:${NC}"
echo -e "   Run ${BLUE}just${NC} or ${BLUE}just help${NC} to see all available commands"
echo ""
