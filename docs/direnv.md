# direnv setup for InfraFoundry

## What is direnv?

[direnv](https://direnv.net/) is a shell extension that automatically loads/unloads environment variables based on the current directory. It makes working with environment-specific settings seamless.

## Installation

### macOS
```bash
brew install direnv
```

### Linux (Debian/Ubuntu)
```bash
sudo apt install direnv
```

### Other systems
See https://direnv.net/docs/installation.html

## Setup

1. **Hook direnv into your shell** (add to `~/.bashrc`, `~/.zshrc`, etc.):

   ```bash
   # Bash
   eval "$(direnv hook bash)"

   # Zsh
   eval "$(direnv hook zsh)"

   # Fish
   direnv hook fish | source
   ```

2. **Allow direnv in this project** (first time only):

   ```bash
   cd /path/to/infrafoundry2
   direnv allow
   ```

3. **Create your personal settings file**:

   ```bash
   cp .envrc.local.example .envrc.local
   # Edit .envrc.local with your actual credentials
   ```

4. **That's it!** Now whenever you `cd` into this project directory:
   - Framework defaults from `.envrc` load automatically
   - Your personal settings from `.envrc.local` override defaults
   - Credentials stay local and git-ignored

## Usage

### Automatic loading
```bash
cd ~/projects/infrafoundry2
# Output: 🔧 InfraFoundry environment loaded
#         Config: envs
#         Secrets: secrets
#         Output: generated
```

### Reload after changes
```bash
# After editing .env or .envrc
direnv reload
```

### Check loaded variables
```bash
direnv status
printenv | grep INFRAFOUNDRY
```

### Disable temporarily
```bash
direnv deny
# To re-enable:
direnv allow
```

## Benefits for InfraFoundry

1. **Clean separation**:
   - `.envrc` = framework defaults (version-controlled)
   - `.envrc.local` = your credentials and preferences (git-ignored)
2. **No manual exports**: Automatically sets all environment variables
3. **Environment isolation**: Variables only active in this project directory
4. **Team consistency**: Everyone uses the same `.envrc`, customizes via `.envrc.local`
5. **CI/CD compatibility**: CI uses traditional env vars, local dev uses direnv
6. **Security warnings**: Alerts if SOPS keys are missing

## File Structure

```
.envrc                  # Framework defaults (committed to git)
.envrc.local           # Your personal settings (git-ignored)
.envrc.local.example   # Template for .envrc.local (committed to git)
.env.example           # Legacy, kept for CI/CD compatibility
```

## Advanced: Customizing .envrc.local

Your `.envrc.local` can override any defaults and add credentials:

```bash
# .envrc.local - personal settings
export INFRAFOUNDRY_LOG_LEVEL=DEBUG
export TF_LOG=DEBUG

# Proxmox credentials
export PROXMOX_API_URL=https://proxmox.local:8006/api2/json
export PROXMOX_API_TOKEN_ID=myuser@pam!mytoken
export PROXMOX_API_TOKEN_SECRET=abc123-secret

# Use a custom Python environment
layout python python3.11
```

**Never commit `.envrc.local`** - it's git-ignored by default.

## CI/CD Note

direnv is for **local development only**. CI/CD pipelines should still use:
- GitHub Secrets / GitLab CI/CD variables
- The `ci/setup-ci.sh` script handles CI environment setup
