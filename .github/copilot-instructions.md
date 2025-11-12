# InfraFoundry - AI Coding Agent Instructions

## Project Overview
InfraFoundry is an infrastructure code generator and orchestration framework that generates Terraform and Ansible configurations from YAML definitions. It's built with Python 3.12+, uses uv for package management, and supports Proxmox, OPNsense, and Kubernetes providers.

**What InfraFoundry Does:**
1. **Primary: Code Generation** - Reads YAML configs, generates Terraform `.tf` files and Ansible playbooks
2. **Secondary: Tool Orchestration** - Optionally executes `terraform` and `ansible-playbook` commands
3. **Does NOT** replace Terraform/Ansible - it generates standard configs and orchestrates their execution

**Important:** InfraFoundry separates framework code (this repository) from user infrastructure configurations (separate repositories). This allows independent versioning, private configs with public framework, and better access control.

## Quick Orientation

### Key Files to Check First
1. `src/infrafoundry/core/` - Core framework (provider base, config/secret managers, orchestrator)
2. `src/infrafoundry/providers/` - Provider plugins (proxmox, opnsense, kubernetes)
3. `example-config/` - Example configuration repository structure
4. `docs/separate-config-repo.md` - Separate config repo pattern guide
5. `docs/state-management.md` - State management strategies and best practices
6. `docs/per-environment-credentials.md` - Managing different credentials per environment
7. `pyproject.toml` - Dependencies and project metadata
8. `README.md` - Complete project documentation

### Architecture

**Repository Structure:**
- **Framework Repository** (this repo): Core code, provider plugins, templates
- **Configuration Repository** (separate): User's infrastructure configs, secrets

**Two-layer design:**

1. **Code Generation Layer**:
   - `provider.py`: `ProviderBase` - abstract class all providers implement
   - `config.py`: `ConfigManager` - loads YAML configs (supports `INFRAFOUNDRY_CONFIG_REPO`)
   - `secrets.py`: `SecretManager` - SOPS/age encryption (supports `INFRAFOUNDRY_CONFIG_REPO`)
   - Providers: Generate Terraform `.tf` files and Ansible playbooks from templates
   - Templates: Jinja2 templates in `providers/{name}/templates/`

2. **Orchestration Layer**:
   - `orchestrator.py`: `Orchestrator` - coordinates multi-provider deployments, runs terraform/ansible
   - `cli.py`: Click-based CLI with `--config-dir` option
   - `state.py`: SQLite database for deployment tracking
   - `events.py`: Event system for notifications and hooks

**State Management** (see `docs/state-management.md`):
- **Terraform State**: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` - Infrastructure resource state
- **InfraFoundry State**: `~/.infrafoundry/state.db` - Deployment history, audit trail, rollback data
- **Generated Configs**: `generated/{env}/` - Reproducible from YAML, git-ignored
- Environment isolation prevents state conflicts between dev/staging/prod

**Providers** (`src/infrafoundry/providers/`):
- Each provider (proxmox, opnsense, kubernetes) implements `ProviderBase`
- `generate_terraform()` - renders Jinja2 templates to `.tf` files
- `generate_ansible()` - renders Jinja2 templates to playbooks
- Templates live in `src/infrafoundry/providers/{name}/templates/{name}/`

**Configurations** (separate repo or `example-config/`):
- `envs/{env}/settings.yaml` - environment config + provider credentials (supports SOPS encryption)
- **Provider-centric** (original): `envs/{env}/{provider}/{resource_type}.yaml` - resource definitions
- **Resource-centric** (new): `envs/{env}/resources/*.yaml` - multi-provider resource definitions
- **Note:** Providers are auto-discovered from resources; no need to declare them

**Data flow:**
```
YAML configs → ConfigManager → Orchestrator → Providers → Jinja2 → generated/*.tf
                                                                   ↓
                                                    (optional) terraform init/apply
                                                                   ↓
                                                              Infrastructure
```

**Commands:**
- `infra plan` - Generate configs only (no execution)
- `infra apply` - Generate + execute terraform/ansible
- `infra destroy` - Execute terraform destroy

### Build / Run / Test

**Framework development:**

**CRITICAL: Always use `uv` for Python package management!**
- Use `uv pip install` instead of `pip install`
- Use `uv pip uninstall` instead of `pip uninstall`
- Use `uv pip list` instead of `pip list`
- Never use plain `pip` - it may install to wrong environment

```bash
# Setup
uv pip install -e .              # Install package in editable mode
cp docs/examples/.envrc.local.example .envrc.local  # Set up direnv
direnv allow                     # Load environment

# Development
make dev                         # Install with dev dependencies (uses uv)
make test                        # Run pytest (286 tests)
make coverage                    # Run tests with full coverage report (70%)
make lint                        # Run ruff
make format                      # Format with black

# Adding dependencies
uv pip install <package>         # Install new package
# Then update pyproject.toml manually or regenerate with:
uv pip freeze > requirements.txt

# Infrastructure operations (with separate config repo)
export INFRAFOUNDRY_CONFIG_REPO="/path/to/config-repo"
infra envs                       # List environments
infra list --env dev             # List all resources
infra plan --env dev             # Generate Terraform
infra plan --env dev --resource web-01  # Target specific resource
infra apply --env dev            # Apply infrastructure
infra status --env dev           # Check deployment status
infra destroy --env dev          # Tear down

# Or use --config-dir flag
infra --config-dir /path/to/config-repo envs

# Secret management
infra secrets init               # Generate age key
infra secrets encrypt file.yaml  # Encrypt with SOPS
infra secrets decrypt file.yaml  # Decrypt and display
```

### Project-Specific Conventions

**1. Repository Separation:**
- **Framework repo** (this repo): Core code, providers, templates
- **Config repo** (separate): Environments, resources, secrets
- Set `INFRAFOUNDRY_CONFIG_REPO` to point to config repo
- Or use `--config-dir` CLI flag on every command
- ConfigManager/SecretManager check env var first, fall back to local dirs
- **CLI precedence**: `--config-dir` flag > `INFRAFOUNDRY_CONFIG_REPO` env var > default `./envs`

**2. Configuration Files:**
- Supports **two formats** for organizing resources:

  **Provider-Centric** (traditional):
  - Files organized by provider: `envs/{env}/{provider}/`
  - Resource type from filename: `vm.yaml`, `firewall_rule.yaml`
  - Multiple files per type: `vm.yaml`, `vm-services.yaml` (both type `vm`)
  - Use singular names for resource types: `vm:`, `deployment:`, `firewall_rule:`

  **Resource-Centric** (new, recommended for multi-provider):
  - Files in: `envs/{env}/resources/*.yaml`
  - Each resource specifies its provider:
    ```yaml
    resources:
      - provider: proxmox
        type: vm
        name: web-server-01
        config:
          cores: 4
          memory: 8192
    ```
  - Organize by service/application instead of provider
  - See all infrastructure for a service in one file

- Config repo structure: `envs/`, `secrets/`, `.envrc.local`, `.gitignore`, `README.md`
- Both formats can be used simultaneously

**3. Provider Implementation:**
- All providers inherit from `ProviderBase`
- Must implement: `validate_config()`, `generate_terraform()`, `generate_ansible()`, `get_resource_types()`
- Use `@override` decorator (Python 3.12+) on all abstract method implementations
- Templates use Jinja2, stored in `src/infrafoundry/providers/{name}/templates/{name}/`
- Generated files go to `generated/{env}/terraform/{provider}/` and `generated/{env}/ansible/{provider}/`

**4. Environment Variables:**
- Framework-specific: `INFRAFOUNDRY_*` prefix (CONFIG_REPO, CONFIG_DIR, SECRETS_DIR, OUTPUT_DIR, LOG_LEVEL)
- **NEW:** `INFRAFOUNDRY_CONFIG_REPO` - Path to separate config repository
- Application-specific: Use standard names (`PROXMOX_API_URL`, `ANSIBLE_HOST_KEY_CHECKING`)
- Local dev: Use `.envrc.local` (git-ignored) for credentials
- CI/CD: Set via GitHub Secrets / GitLab CI variables

**5. Secret Management:**
- ALL secrets encrypted with SOPS + age
- Age key location: `$INFRAFOUNDRY_CONFIG_REPO/secrets/age.key` or `./secrets/age.key`
- Encrypted files: `secrets/*.yaml` (committed to config repo)
- Export for Terraform: `.tfvars` files (git-ignored)
- CI: Base64-encode age key, store as `SOPS_AGE_KEY`

**6. Code Style:**
- Python 3.12+ type hints (use `list[str]` not `List[str]`, `X | None` not `Optional[X]`)
- Use `@override` decorator for all method overrides (improves type safety)
- Black formatting, ruff linting (enforced in CI)
- Docstrings in Google style
- Max line length: 100 characters

**7. File Naming:**
- Python: snake_case for files/functions/variables
- YAML: kebab-case for resource names (`web-server-01`)
- Terraform resources: Convert to snake_case in templates (`web_server_01`)

**8. Terminal Commands:**
- Use `cat -pp` or `batcat -pp` for displaying file contents (user has batcat installed)
- Plain output without decorations for piping/viewing
- Never use plain `cat` - always include `-pp` flag

**8. Terminal Commands:**
- Use `cat -pp` or `batcat -pp` for displaying file contents (user has batcat installed)
- Plain output without decorations for piping/viewing

### Integration Points & Dependencies

**External Tools:**
- **Terraform** (>= 1.6): Infrastructure provisioning
  - Proxmox: `Telmate/proxmox` provider
  - OPNsense: `browningluke/opnsense` provider
  - Kubernetes: `hashicorp/kubernetes` provider
- **Ansible** (>= 2.15): Post-deployment configuration
- **SOPS** + **age**: Secret encryption/decryption
- **direnv**: Auto-load environment variables (dev only)

**Python Dependencies** (see `pyproject.toml`):
- click - CLI framework
- pyyaml - YAML parsing
- jinja2 - Template rendering
- pydantic - Config validation
- rich - Terminal formatting
- python-dotenv - .env loading

**State Management:**
- Terraform state: Local by default, configurable via `INFRAFOUNDRY_TF_BACKEND_TYPE`
- For production: Use S3, Terraform Cloud, or other remote backend

### CI/CD Integration

**GitHub Actions** (`.github/workflows/infra-deploy.yml`):
- Triggered on: push to main, manual workflow_dispatch
- Sets up: Python, uv, Terraform, Ansible, SOPS
- Decodes `SOPS_AGE_KEY` secret to `secrets/age.key`
- Runs: `infra plan` → `infra apply --auto-approve`

**GitLab CI** (`docs/examples/.gitlab-ci.yml.example`):
- Stages: validate → plan → apply
- Manual approval for apply stages
- Environment-specific jobs (dev, prod)

**CI Setup Script** (`ci/setup-ci.sh`):
- Validates required tools
- Creates age key from `SOPS_AGE_KEY` env var
- Sets default INFRAFOUNDRY_* variables
- Run before any infra commands in CI

### Common Development Workflows

**Choosing configuration format:**
- **Provider-centric**: Best for simple, single-provider setups (e.g., all Proxmox VMs)
- **Resource-centric**: Best for complex multi-provider services (e.g., VM + firewall + DNS)
- Both formats can coexist in the same environment

**Adding a new provider:**
1. Create `src/infrafoundry/providers/newprovider/__init__.py` implementing `ProviderBase`
2. Add templates in `providers/newprovider/templates/newprovider/`
3. Register in `src/infrafoundry/cli.py` `_get_orchestrator()` function
4. Create example configs in `envs/dev/newprovider/` or `envs/dev/resources/`
5. Provider will be auto-discovered when resources are found

**Adding a new resource type to existing provider:**
1. Create `envs/dev/{provider}/{resource_type}.yaml` example
2. Add Jinja2 template `providers/{provider}/templates/{provider}/{resource_type}.tf.j2`
3. Add generation method `_generate_{resource_type}_terraform()` in provider class
4. Update `get_resource_types()` to include new type
5. Update `get_dependencies()` if there are dependencies

**Testing changes locally:**
```bash
# After editing configs or provider code
make format                      # Format code
infra plan --env dev --dry-run   # Check what would be generated
infra plan --env dev             # Generate Terraform files
cd generated/dev/terraform/{provider}
terraform plan                   # Review Terraform plan
```

### Debugging Tips

**Configuration loading issues:**
- Check `infra envs` to list available environments
- Verify YAML syntax with `python -c "import yaml; yaml.safe_load(open('file.yaml'))"`
- Enable debug logging: `export INFRAFOUNDRY_LOG_LEVEL=DEBUG`

**Secret decryption issues:**
- Verify `SOPS_AGE_KEY_FILE` points to correct key: `echo $SOPS_AGE_KEY_FILE`
- Test SOPS manually: `sops --decrypt secrets/proxmox.yaml`
- Check `.sops.yaml` has correct age public key

**Provider not found:**
- Check provider is registered in `cli.py` `_get_orchestrator()`
- Verify provider class is importable: `python -c "from infrafoundry.providers.proxmox import ProxmoxProvider"`
- Check templates directory exists: `ls src/infrafoundry/providers/{name}/templates/`

**Generated Terraform errors:**
- Review generated files in `generated/{env}/terraform/{provider}/`
- Check Jinja2 template syntax in `providers/{provider}/templates/`
- Validate with `terraform validate` in generated directory

### Important Patterns

**Resource dependencies:** Providers can declare dependencies via `get_dependencies()`:
```python
def get_dependencies(self) -> dict[str, list[str]]:
    return {
        "vm": ["template", "network"],  # VMs depend on templates and networks
        "firewall_rule": ["alias"],      # Rules depend on aliases
    }
```

**Terraform + Ansible workflow:**
1. `generate_terraform()` creates infrastructure
2. Terraform outputs (IPs, IDs) available to Ansible
3. `generate_ansible()` creates post-config playbooks
4. Ansible runs after Terraform apply

**Secret sharing:** Secrets in `secrets/*.yaml` are decrypted and exported to both Terraform (`.tfvars`) and Ansible (`vars.yml`) automatically by `SecretManager`.

### When to Edit Which Files

**Core Framework Changes:**
- `src/infrafoundry/core/provider.py` - Modify provider interface
- `src/infrafoundry/core/orchestrator.py` - Change deployment workflow
- `src/infrafoundry/core/config.py` - Alter config loading
- `src/infrafoundry/cli.py` - Add CLI commands

**Provider Changes:**
- `src/infrafoundry/providers/{name}/__init__.py` - Provider logic
- `providers/{name}/templates/` - Terraform/Ansible templates

**Configuration Changes:**
- `envs/{env}/settings.yaml` - Environment definition + provider settings
- `envs/{env}/{provider}/*.yaml` - Provider-centric resource definitions
- `envs/{env}/resources/*.yaml` - Resource-centric resource definitions

**CI/CD Changes:**
- `.github/workflows/` - GitHub Actions
- `docs/examples/.gitlab-ci.yml.example` - GitLab CI
- `ci/setup-ci.sh` - CI environment setup

### Contact & Resources

- Main documentation: `README.md`
- direnv setup: `docs/direnv.md`
- CI/CD guide: `ci/README.md`
- Example configs: `envs/dev/`

### Important: Root Directory Management

**DO NOT place files in the root directory unless they are essential project files:**

**Allowed in root:**
- Configuration files: `pyproject.toml`, `.gitignore`, `.envrc.local.example`, etc.
- Documentation: `README.md`, `LICENSE`, `CHANGELOG.md`
- Build/tooling: `Makefile`, `pytest.ini`, etc.
- CI/CD: `.github/`, `.gitlab-ci.yml`

**NOT allowed in root:**
- Test scripts (`test_*.py`) → Use `tmp/` directory (gitignored)
- Temporary files → Use `tmp/` directory (gitignored)
- Example/demo scripts → Use `examples/` or `docs/examples/`
- Development notes → Use `docs/` directory

The root directory should remain clean and only contain files that are part of the project
structure or essential for project operations. All temporary or experimental files belong
in `tmp/` which is already in `.gitignore`.

When making changes, always:
1. Run `make format` and `make lint`
2. Test with `infra plan --env dev --dry-run` first
3. Update documentation if adding features
4. Add example configs for new resource types
5. Keep the root directory clean - use `tmp/` for temporary files
