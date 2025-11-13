# Claude AI Assistant Context for InfraFoundry

## Project Overview

**InfraFoundry** is a pluggable infrastructure code generator and orchestration framework for Terraform and Ansible. It generates Terraform `.tf` files and Ansible playbooks from YAML configurations, then optionally orchestrates their execution.

**Key Principle:** Users write only YAML - InfraFoundry automatically generates all Terraform and Ansible files. No HCL knowledge required!

---

## Project Structure

```
infrafoundry/
├── src/infrafoundry/
│   ├── core/                    # Core framework
│   │   ├── config/             # Configuration management (package)
│   │   ├── state/              # State management (package)
│   │   ├── dependencies/       # Dependency resolution (package)
│   │   ├── policy/             # Policy enforcement (package)
│   │   ├── validation_helpers/ # Validation framework (package)
│   │   ├── notifications/      # Notification system (package)
│   │   ├── runners/            # Pluggable runner system (package)
│   │   ├── orchestrator.py     # Main orchestration (973 lines - needs refactoring)
│   │   ├── base_manager.py     # BaseManager and PathBasedManager
│   │   ├── provider_mixins.py  # Provider mixin patterns
│   │   ├── drift_detector.py   # Drift detection (140 lines)
│   │   ├── deployment_executor.py # Deployment execution (269 lines)
│   │   ├── policy_checker.py   # Policy validation (132 lines)
│   │   ├── provider_registry.py # Provider auto-discovery (149 lines)
│   │   └── secrets.py          # SOPS secret management
│   │
│   ├── providers/               # Provider plugins
│   │   ├── proxmox/            # Proxmox VE provider (324 lines)
│   │   │   ├── __init__.py
│   │   │   ├── validator.py    # (595 lines - high duplication)
│   │   │   └── templates/
│   │   ├── opnsense/           # OPNsense provider (433 lines)
│   │   │   ├── __init__.py     # ⚠️ Has API call performance bug
│   │   │   ├── validator.py    # (434 lines - high duplication)
│   │   │   ├── services/       # 3-layer architecture
│   │   │   │   ├── base.py
│   │   │   │   ├── kea_dhcp.py # (264 lines)
│   │   │   │   └── isc_dhcp.py
│   │   │   ├── components/
│   │   │   │   ├── base.py
│   │   │   │   ├── kea_dhcp.py # (86 lines)
│   │   │   │   └── isc_to_kea_migration.py # (465 lines - high duplication)
│   │   │   └── templates/
│   │   └── kubernetes/         # Kubernetes provider
│   │       ├── __init__.py
│   │       └── templates/
│   │
│   └── cli/                    # CLI interface
│       ├── main.py
│       └── commands/           # 18 command files (1,400 lines)
│           ├── plan.py
│           ├── apply.py
│           ├── destroy.py
│           ├── drift.py        # Drift detection CLI
│           ├── impact.py       # Impact analysis CLI
│           ├── validate.py     # Pre-flight validation CLI
│           ├── policies.py     # Policy management CLI
│           ├── rollback.py     # Rollback CLI
│           └── ... (13 more)
│
├── tests/                      # Test suite (9,023 lines)
├── docs/                       # Documentation
├── example-config/             # Example configuration repository
└── tools/                      # Utility scripts

**Total Source:** ~13,119 lines
**Total Tests:** ~9,023 lines
**Test Ratio:** 0.69 (good coverage)
```

---

## Architecture Patterns

### 1. **Manager Pattern**
All managers inherit from `BaseManager` or `PathBasedManager`:

```python
# BaseManager provides:
- Standard logging (_log_info, _log_warning, _log_error, _log_debug)
- Error handling (_handle_error)
- Context manager support (__enter__, __exit__)
- Abstract cleanup() method

# PathBasedManager adds:
- Path resolution with env vars (_resolve_path)
- Directory operations (_ensure_directory_exists)
- Path validation (_validate_path_exists)
- Environment variable helper (_get_env_var)
```

**Managers:**
- `ConfigManager(PathBasedManager)` - Configuration loading
- `StateManager(BaseManager)` - Deployment tracking (SQLite/PostgreSQL)
- `SecretManager(PathBasedManager)` - SOPS encryption
- `EventManager(BaseManager)` - Pub/sub event system
- `NotificationManager(PathBasedManager)` - Notifications

### 2. **Provider Mixin Pattern**
Providers use mixins to reduce duplication:

```python
class ProxmoxProvider(ProviderBase, TemplateRendererMixin, ResourceGrouperMixin):
    # TemplateRendererMixin provides:
    - Jinja2 environment setup
    - Template loading and rendering
    - Common filters (to_terraform_name, to_snake_case, to_kebab_case)

    # ResourceGrouperMixin provides:
    - group_resources_by_type()
    - validate_resource_types()
    - get_resource_names_by_type()
    - count_resources_by_type()
```

### 3. **3-Layer Architecture (OPNsense)**
For complex operations:

```
Provider (Thin Delegation - 3 lines)
    ↓
Component Manager (Business Logic/Orchestration)
    ↓
Service Layer (Low-level API Operations)
    ↓
API Client
```

**Example:**
- `OPNsenseProvider.reset_kea_dhcpv4()` → `KeaDHCPManager.reset_dhcpv4()` → `KeaDHCPService.delete_dhcpv4_subnet()`

### 4. **Pluggable Runner System**
Extensible tool support:

```python
BaseRunner (abstract)
├── TerraformRunner - Terraform operations
├── AnsibleRunner - Ansible operations
└── PulumiRunner - Pulumi operations (example)
```

### 5. **Event-Driven Architecture**
Pub/sub pattern throughout:

```python
EventType:
- DRIFT_CHECK_STARTED, DRIFT_DETECTED, DRIFT_CHECK_COMPLETED
- POLICY_CHECK_STARTED, POLICY_VIOLATION, POLICY_CHECK_PASSED
- RESOURCE_CREATING, RESOURCE_CREATED, RESOURCE_DELETED
- BEFORE_PLAN, AFTER_PLAN, PLAN_FAILED
- BEFORE_APPLY, AFTER_APPLY, APPLY_FAILED
```

---

## State Management

### Three Types of State:

1. **Terraform State** (per-environment, per-provider)
   - Location: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`
   - Backends: Local (default), S3, Terraform Cloud, Azure

2. **InfraFoundry State** (global deployment history)
   - Location: `~/.infrafoundry/state.db` (SQLite) or PostgreSQL
   - Tracks: deployments, resources, lifecycle, dependencies, events
   - Schema: deployments, resources, resource_dependencies, deployment_events

3. **Generated Configurations** (temporary, reproducible)
   - Location: `generated/{env}/{terraform|ansible}/{provider}/`
   - Git-ignored, regenerated on demand

---

## Current Technical Debt (Prioritized)

### 🔴 **CRITICAL - Phase 1 (Weeks 1-2)**

1. ✅ **API Call Performance Bug - COMPLETED (2025-01-13)**
   - File: `providers/opnsense/__init__.py` lines 118-280
   - Issue: ~~Creates 60 API clients for 10 subnets + 50 reservations~~
   - Impact: ~~60x slower than needed~~ **FIXED - 98% reduction in API calls**
   - Solution: Created `_generate_kea_dhcp6_resources()` that batches all operations
   - Performance: 60 API clients → 1, 60 searches → 2, 2 reconfigs → 1

2. **Orchestrator God Object**
   - File: `core/orchestrator.py` (973 lines)
   - Most complex: `validate()` - complexity 21, 144 lines
   - Fix: Split into ValidationOrchestrator, PlanningOrchestrator, etc.

3. **Silent Failures**
   - Missing cloud-init snippets: prints warning, continues
   - Missing secrets: logs warning, continues deployment
   - Fix: Add strict mode configuration

### 🟡 **HIGH - Phase 2 (Weeks 3-4)**

4. **Provider Code Duplication (~200 lines)**
   - Files: All provider `__init__.py` files
   - Issue: `_generate_tfvars()` duplicated 3x (40+ lines each)
   - Fix: Create `TerraformGeneratorMixin`

5. **Validator Code Duplication (~150 lines)**
   - Files: `proxmox/validator.py` (595 lines), `opnsense/validator.py` (434 lines)
   - Issue: Connectivity validation, credential retrieval duplicated
   - Fix: Create `BaseAPIValidator` mixin

6. **CLI Command Boilerplate (~100 lines)**
   - Files: All 18 `cli/commands/*.py` files
   - Issue: Identical error handling and orchestrator initialization
   - Fix: Create `@with_orchestrator` decorator, `CommandBase` class

### 🟢 **MEDIUM - Phase 3 (Weeks 5-6)**

7. **Type Safety Issues**
   - 11 files using `Any` excessively
   - Missing return type annotations
   - Fix: Add proper types, enable mypy strict mode

8. **Error Handling Inconsistency**
   - Generic `except Exception` in 18+ places
   - Missing error context
   - Fix: Create exception hierarchy, specific catches

9. **Missing Caching**
   - `ConfigManager.load_environment()` - no caching
   - `StateManager` queries - no caching
   - Fix: Add LRU caching with `@lru_cache` and cache dicts

---

## Complexity Hotspots (Target: <10)

| Complexity | File | Function | Current Lines | Issue |
|-----------|------|----------|---------------|-------|
| **21** | orchestrator.py:228 | validate() | 144 | Too many responsibilities |
| **20** | proxmox/validator.py:178 | _collect_resource_references() | 90 | Deep nesting, multiple types |
| **19** | isc_to_kea_migration.py:245 | _convert_dhcpv6_subnet() | 85 | 90% duplicate of v4 |
| **18** | kea_dhcp.py:155 | export_to_yaml() | 95 | Mixed concerns |
| **16** | isc_to_kea_migration.py:66 | _convert_dhcpv4_subnet() | 79 | Should share with v6 |
| **15** | proxmox/__init__.py:94 | _process_cloud_init_snippets() | 79 | Deep nesting, mixed concerns |

---

## Implemented Features (Fully Production-Ready)

All these have CLI commands and complete implementations:

- ✅ **Drift Detection** - `infra drift --env prod`
- ✅ **Impact Analysis** - `infra impact --env prod --resource db-template`
- ✅ **Pre-flight Validation** - `infra validate --env test`
- ✅ **Policy Enforcement** - `infra policies list/check`
- ✅ **Parallel Execution** - Built into DeploymentExecutor
- ✅ **Automated Rollback** - `infra rollback --env prod --to-deployment 42`
- ✅ **Provider Auto-Discovery** - Automatic registration
- ✅ **Migration Tools** - ISC to Kea DHCP migration

---

## Development Guidelines

### When Refactoring:

1. **Always Read Files First**
   - Use Read tool before Edit/Write
   - Understand context before making changes

2. **Maintain Backward Compatibility**
   - All refactorings should be non-breaking
   - Keep existing public APIs
   - Use deprecation warnings if needed

3. **Follow Established Patterns**
   - Use BaseManager/PathBasedManager for new managers
   - Use provider mixins for providers
   - Follow 3-layer architecture for complex operations

4. **Type Safety**
   - Add type hints to all new code
   - Use specific types, avoid `Any`
   - Add return type annotations

5. **Error Handling**
   - Use specific exception types
   - Provide context in error messages
   - Log before raising when appropriate
   - Don't catch KeyboardInterrupt/SystemExit

6. **Testing**
   - Maintain 70% coverage threshold
   - Add tests for refactored code
   - Use fixtures for common test data
   - Mock external dependencies

7. **Documentation**
   - Update docs when changing behavior
   - Add docstrings to new functions
   - Document breaking changes

### Code Style:

```python
# Good: Specific types
def track_resource(
    self,
    info: ResourceTrackingInfo
) -> Resource:
    ...

# Bad: Generic types
def track_resource(
    self,
    deployment_id,
    environment,
    provider,
    ...
) -> Any:
    ...

# Good: Specific exceptions
try:
    provider.validate()
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
    raise
except ValueError as e:
    logger.warning(f"Invalid config: {e}")
    raise

# Bad: Generic exceptions
try:
    provider.validate()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

# Good: Early returns
def validate_config(config: dict) -> bool:
    if not config:
        logger.error("Config is empty")
        return False

    if "name" not in config:
        logger.error("Missing 'name' field")
        return False

    return True

# Bad: Deep nesting
def validate_config(config: dict) -> bool:
    if config:
        if "name" in config:
            if config["name"]:
                return True
    return False
```

---

## Key Files Reference

### Core Files (Most Important)
- `core/orchestrator.py` (973 lines) - Main coordinator ⚠️ Needs refactoring
- `core/base_manager.py` - BaseManager pattern
- `core/provider_mixins.py` - Provider mixins
- `core/state/state_manager.py` - State tracking
- `core/events.py` - Event system
- `core/dependencies/` - Dependency resolution

### Provider Files
- `providers/proxmox/__init__.py` (324 lines)
- `providers/opnsense/__init__.py` (433 lines) ⚠️ Has performance bug
- `providers/kubernetes/__init__.py`

### Validators (High Duplication)
- `providers/proxmox/validator.py` (595 lines)
- `providers/opnsense/validator.py` (434 lines)

### CLI
- `cli/main.py` - CLI entry point
- `cli/commands/` - 18 command files

---

## Environment Variables

Common environment variables used throughout:

```bash
# Required
INFRAFOUNDRY_CONFIG_REPO    # Path to configuration repository

# Optional
INFRAFOUNDRY_OUTPUT_DIR     # Generated files location (default: generated/)
INFRAFOUNDRY_STATE_BACKEND  # sqlite (default) or postgresql
INFRAFOUNDRY_STATE_CONNECTION # Custom DB connection string
INFRAFOUNDRY_LOG_LEVEL      # DEBUG, INFO, WARNING, ERROR
SOPS_AGE_KEY_FILE          # Age encryption key for SOPS

# Provider credentials (per-environment)
PROXMOX_API_URL
PROXMOX_API_TOKEN_ID
PROXMOX_API_TOKEN_SECRET
OPNSENSE_API_URL
OPNSENSE_API_KEY
OPNSENSE_API_SECRET
```

---

## Testing Information

### Test Structure
- Location: `tests/`
- Total: 9,023 lines
- Coverage: 70% (passing threshold: 69%)
- Test ratio: 0.69 (good)

### Running Tests

**Important:** This project uses `uv` for Python environment management.

```bash
# Run tests using uv
uv run pytest                              # Run all tests
uv run pytest tests/unit/test_*.py -v    # Run specific tests
uv run pytest --cov                        # Run with coverage report

# Or use make (which calls uv internally)
make test          # Run all tests
make coverage      # Run with coverage report
make lint          # Run linting
make format        # Format code
```

### Test Patterns
- Use fixtures in `tests/fixtures/`
- Mock external dependencies (Terraform, Ansible, APIs)
- Follow existing patterns in `tests/unit/`
- Use pytest for all tests

---

## Common Workflows

### Development Workflow
```bash
# 1. Install dependencies (uv manages the environment)
uv sync                # Sync dependencies from pyproject.toml
# or
uv pip install -e .    # Install in editable mode

# 2. Make changes
# ... edit code ...

# 3. Run tests
uv run pytest          # Direct pytest
# or
make test              # Via Makefile

# 4. Format and lint
make format
make lint

# 5. Check coverage
uv run pytest --cov
# or
make coverage
```

### Deployment Workflow
```bash
# 1. List environments
infra envs

# 2. Validate configuration
infra validate --env dev

# 3. Preview changes
infra plan --env dev

# 4. Check for drift
infra drift --env dev

# 5. Apply changes
infra apply --env dev

# 6. View history
infra history --env dev
```

---

## Important Notes

### What Makes This Project Unique
1. **YAML-only configuration** - No HCL required
2. **Separation of framework from config** - Two-repo pattern
3. **Advanced features fully implemented** - Not just foundations
4. **Event-driven architecture** - Hooks everywhere
5. **Pluggable everything** - Providers, runners, validators, policies

### What NOT to Change
- Public CLI command interfaces
- BaseManager/PathBasedManager APIs
- Provider plugin interfaces
- State database schema (use migrations)
- Event type enums (additive only)

### When to Ask Questions
- Before breaking backward compatibility
- When unsure about architectural decisions
- When test coverage drops below 69%
- When adding new dependencies

---

## Git Commit Conventions

### Commit Message Format

This project follows **Conventional Commits** format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Commit Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring (no functional changes)
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (deps, config, etc.)
- `perf`: Performance improvements
- `style`: Code style/formatting changes

### Scope (Optional)
- Component or module affected: `opnsense`, `proxmox`, `cli`, `orchestrator`, etc.

### Commit Message Style

**Short commits (simple changes):**
```bash
git commit -m "chore: update uv.lock"
git commit -m "fix(cli): handle missing environment gracefully"
git commit -m "docs: fix typo in README"
```

**Detailed commits (significant changes):**
```bash
git commit -m "$(cat <<'EOF'
refactor(opnsense): batch DHCPv6 API calls for 98% performance improvement

### Problem
- Created API client inside loop for EVERY subnet/reservation
- Called search functions N times instead of once
- Result: 60x performance overhead

### Solution
- Created batched method that processes all resources together
- Single API client creation
- Single search per resource type
- Single service reconfiguration

### Performance Improvements
- API clients: 60 → 1 (98% reduction)
- Searches: 60 → 2 (97% reduction)
- Reconfigs: 2 → 1 (50% reduction)

### Testing
- All 449 tests passing
- Backward compatible
- No breaking changes

Addresses REFACTORING_TODO.md #1
EOF
)"
```

### Commit Structure for Significant Changes

Use markdown formatting in commit body:

1. **Problem Statement**
   - Describe what was wrong or missing
   - Include metrics/impact if applicable

2. **Solution**
   - Explain the approach taken
   - List key implementation details

3. **Changes/Impact**
   - List specific changes made
   - Document any breaking changes

4. **Testing**
   - Test results
   - Backward compatibility notes
   - Risk assessment

5. **References** (optional)
   - Link to issues, docs, or TODO items

### Examples from Project History

**Refactoring:**
```
refactor: per-environment secrets migration complete

### Architecture Changes
- ConfigManager now requires INFRAFOUNDRY_CONFIG_REPO
- SecretManager takes env_name parameter
- Updated all paths from secrets/ to envs/{env}/

### Test Fixes (453 tests passing)
- Updated all test instantiations
- Fixed path references

### Documentation Updates
- Removed deprecated secrets/ references
- Updated security best practices
```

**Feature:**
```
feat(opnsense): add Kea DHCP support and reset/migrate methods

- Add reset_kea_dhcpv4() and reset_kea_dhcpv6()
- Add migrate_kea_dhcp() for config export
- Delegate to KeaDHCPManager component
- All tests passing
```

**Documentation:**
```
docs: update documentation to reflect fully implemented features

### Overview
Updated docs to show advanced features are production-ready

### Changes
- README.md: Added "Advanced Operations" section
- CLI_REFERENCE.md: Complete CLI command reference
- Architecture docs updated

### Impact
- Improves feature discoverability
- Clarifies production-ready status
```

### Multi-Commit Strategy

When working on related changes, create separate commits for:

1. **Core refactoring** - The main code changes
2. **Documentation** - Doc updates related to the refactoring
3. **Tests** - New or updated tests (if not part of refactoring)
4. **Cleanup** - Formatting, minor fixes
5. **Dependencies** - uv.lock, package updates

**Example sequence:**
```bash
# 1. Main refactoring
git add src/infrafoundry/providers/opnsense/__init__.py
git commit -m "refactor(opnsense): batch DHCPv6 API calls..."

# 2. Documentation
git add .claude/ REFACTORING_TODO.md
git commit -m "docs: add Claude context and update refactoring status..."

# 3. Related docs
git add README.md docs/
git commit -m "docs: update feature documentation..."

# 4. Cleanup
git add example-config/ ci/
git commit -m "chore: update CI script and example configs..."

# 5. Dependencies
git add uv.lock
git commit -m "chore: update uv.lock"
```

### Tips for Good Commits

✅ **Do:**
- Use present tense ("add feature" not "added feature")
- Be specific in scope (component/module affected)
- Include metrics for performance improvements
- Reference related issues or docs
- Use markdown formatting for complex commits
- Keep each commit focused on one logical change

❌ **Don't:**
- Mix unrelated changes in one commit
- Use vague messages ("fix stuff", "updates")
- Skip the body for significant changes
- Include work-in-progress commits in main branches
- Commit without running tests

---

## Quick Reference: File Sizes

```
Large files (>400 lines):
orchestrator.py          973 lines ⚠️
proxmox/validator.py     595 lines ⚠️
isc_to_kea_migration.py  465 lines
opnsense/__init__.py     433 lines ⚠️
opnsense/validator.py    434 lines
proxmox/__init__.py      324 lines

Target: All files <400 lines
```

---

## Useful Commands for Claude

```bash
# Find files matching pattern
find src/infrafoundry -name "*.py" | grep validator

# Count lines in file
wc -l src/infrafoundry/core/orchestrator.py

# Search for pattern
grep -r "Exception as e" src/infrafoundry/

# List all CLI commands
ls src/infrafoundry/cli/commands/*.py

# Run specific test (use uv)
uv run pytest tests/unit/test_orchestrator.py -v

# Check test coverage for file (use uv)
uv run pytest --cov=src/infrafoundry/core/orchestrator.py tests/

# Run InfraFoundry CLI commands (use uv)
uv run infra --help
uv run infra validate --env dev
```

---

## Current Refactoring Status

### Phase 1 (In Progress - Started 2025-01-13)
- ✅ **#1: API Call Performance Bug** - COMPLETED
  - Batched DHCPv6 operations in OPNsense provider
  - 98% reduction in API calls (60→1 clients, 60→2 searches, 2→1 reconfigs)
  - All 449 tests passing
  - Backward compatible implementation
- ⏳ **#2: Orchestrator Complexity** - Next priority
  - Split 973-line orchestrator into specialized orchestrators
  - Target: ValidationOrchestrator, PlanningOrchestrator, etc.
- ⏳ **#3: Silent Failures** - Queued
  - Add strict mode configuration
  - Configurable error vs. warning behavior

### Previous Accomplishments (Phase 0)
- ✅ Documentation updated to reflect implemented features
- ✅ Comprehensive analysis completed (13,119 source + 9,023 test lines)
- ✅ 11 major refactorings completed (CLI, State, Config, Managers, Providers)
- ✅ All managers standardized with BaseManager pattern
- ✅ Provider mixins created (TemplateRenderer, ResourceGrouper)

**Next Steps:** Continue Phase 1 - orchestrator split, then silent failures fix

---

## Contact & Resources

- **Repository:** https://github.com/endavis/infrafoundry
- **Documentation:** `/docs/`
- **Issues:** GitHub Issues
- **Tests:** `make test`
- **Coverage:** `make coverage`

---

## Environment Management

**This project uses `uv` for Python environment management.**

`uv` is a fast Python package installer and resolver. Key points:
- Automatically manages virtual environments
- Use `uv run <command>` to run commands in the project environment
- Use `uv sync` to install/update dependencies from `pyproject.toml`
- No need to manually activate virtual environments

Examples:
```bash
# Run tests
uv run pytest

# Run CLI
uv run infra --help

# Install dependencies
uv sync
```

---

*Last Updated: 2025-01-13*
*Claude Context Version: 1.1*
