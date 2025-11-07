# Separate Configuration Repository - Implementation Summary

## What Changed

InfraFoundry now supports (and recommends) keeping infrastructure configurations in a separate repository from the framework code.

## Benefits

- **Independent Versioning**: Update framework without affecting configs
- **Access Control**: Different permissions for framework vs infrastructure
- **Privacy**: Keep configs private while using public/shared framework
- **Multi-Project**: Share one framework across multiple config repos
- **Team Collaboration**: Clear separation of responsibilities

## Architecture

```
Before (Embedded):                After (Separated):
infrafoundry/                     infrafoundry/              my-config/
├── src/                          ├── src/                   ├── envs/
├── envs/                         ├── example-config/        ├── secrets/
├── secrets/                      └── docs/                  └── .envrc.local
└── .envrc.local

Single repo, mixed concerns       Framework repo             Config repo
```

## Implementation Details

### 1. Core Changes

**ConfigManager** (`src/infrafoundry/core/config.py`):
- Checks `INFRAFOUNDRY_CONFIG_REPO` environment variable
- Falls back to `INFRAFOUNDRY_CONFIG_DIR` or `./envs/`
- Looks for configs in `$INFRAFOUNDRY_CONFIG_REPO/envs/`

**SecretManager** (`src/infrafoundry/core/secrets.py`):
- Checks `INFRAFOUNDRY_CONFIG_REPO` environment variable
- Falls back to `INFRAFOUNDRY_SECRETS_DIR` or `./secrets/`
- Looks for secrets in `$INFRAFOUNDRY_CONFIG_REPO/secrets/`

### 2. CLI Updates

**New --config-dir option:**
```bash
infra --config-dir /path/to/config envs
infra --config-dir /path/to/config plan --env dev
```

**Updated commands:**
- All commands (`plan`, `apply`, `destroy`, `status`, `envs`) support `--config-dir`
- Respects `INFRAFOUNDRY_CONFIG_REPO` environment variable
- Backward compatible with embedded configs

### 3. Example Configuration Repository

Created `example-config/` directory with:
- `envs/` - Example environment configurations (copied from original)
- `secrets/` - Example secrets structure
- `.gitignore` - Config repo gitignore (secrets, generated files)
- `.envrc.local.example` - Environment variable template
- `README.md` - Complete config repo documentation (350+ lines)

### 4. Documentation

**New Documentation:**
- `docs/separate-config-repo.md` - Comprehensive guide (500+ lines)
  - Setup methods (env var, CLI flag, legacy)
  - Directory structure examples
  - CI/CD integration (GitHub Actions, GitLab CI)
  - Team collaboration patterns
  - Migration guide from embedded config
  - Troubleshooting

- `ci/separate-config-ci.md` - CI/CD specific guide
  - GitHub Actions workflow example
  - GitLab CI configuration
  - Required secrets setup
  - Best practices

**Updated Documentation:**
- `README.md` - Added architecture section, updated quick start
- `.github/copilot-instructions.md` - Added config repo pattern, updated conventions
- `example-config/README.md` - Config repo setup and usage

### 5. Git Ignore Updates

**Framework repo** (`.gitignore`):
- Now ignores `envs/` and `secrets/` directories
- Allows `example-config/**/*.yaml`
- Encourages separate config repos

**Config repo** (`example-config/.gitignore`):
- Ignores `secrets/*.key` and `secrets/*.yaml`
- Ignores `.envrc.local`
- Ignores `generated/` directory
- Allows `secrets/.gitkeep` and `*.yaml.example`

## Usage Patterns

### Pattern 1: Environment Variable (Recommended)

```bash
# In config repo .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Commands work automatically
infra envs
infra plan --env dev
```

### Pattern 2: CLI Flag

```bash
infra --config-dir /path/to/config plan --env dev
```

### Pattern 3: Legacy (Backward Compatible)

```bash
# No changes needed, works as before
# Configs in ./envs/, secrets in ./secrets/
infra plan --env dev
```

## Migration Path

### For Existing Users

1. **Create config repository:**
   ```bash
   cp -r example-config ../my-infrastructure-config
   cd ../my-infrastructure-config
   ```

2. **Copy your configs:**
   ```bash
   cp -r ../infrafoundry/envs/* envs/
   cp -r ../infrafoundry/secrets/* secrets/
   ```

3. **Set up environment:**
   ```bash
   cp .envrc.local.example .envrc.local
   # Edit and add: export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
   ```

4. **Initialize git:**
   ```bash
   git init
   git add .
   git commit -m "Initial infrastructure configuration"
   ```

5. **Test:**
   ```bash
   direnv allow
   infra envs
   infra plan --env dev --dry-run
   ```

See `docs/separate-config-repo.md` for detailed migration instructions.

## Backward Compatibility

✅ **Fully backward compatible:**
- Existing embedded configs still work
- No breaking changes to CLI
- No changes required to existing deployments
- Can migrate at your own pace

## CI/CD Updates

### GitHub Actions

Workflows now checkout both repos:

```yaml
- name: Checkout config repository
  uses: actions/checkout@v4
  with:
    path: config

- name: Checkout InfraFoundry framework
  uses: actions/checkout@v4
  with:
    repository: your-org/infrafoundry
    ref: v0.1.0  # Pin to specific version
    path: infrafoundry
```

See `ci/separate-config-ci.md` for complete examples.

### GitLab CI

Similar pattern - clone framework as dependency:

```yaml
before_script:
  - git clone --depth 1 --branch v0.1.0 https://github.com/your-org/infrafoundry.git
  - cd infrafoundry && uv pip install --system -e . && cd ..
```

## Testing

All features tested and working:

✅ `INFRAFOUNDRY_CONFIG_REPO` environment variable
✅ `--config-dir` CLI flag
✅ Config repo directory structure
✅ Secret management in separate repo
✅ Backward compatibility with embedded configs
✅ Documentation completeness

## Next Steps for Users

1. **Review** `docs/separate-config-repo.md` for full guide
2. **Decide** on separate repo vs embedded config
3. **Create** config repository from `example-config/`
4. **Set up** `INFRAFOUNDRY_CONFIG_REPO` environment variable
5. **Test** with `infra envs` and `infra plan --dry-run`
6. **Update** CI/CD workflows if using separate repo
7. **Share** config repo with team (securely manage age keys)

## Files Changed/Added

### Modified Files
- `src/infrafoundry/core/config.py` - Added `INFRAFOUNDRY_CONFIG_REPO` support
- `src/infrafoundry/core/secrets.py` - Added `INFRAFOUNDRY_CONFIG_REPO` support
- `src/infrafoundry/cli.py` - Added `--config-dir` option, context passing
- `.gitignore` - Now ignores `envs/` and `secrets/` directories
- `README.md` - Added architecture section, updated quick start
- `.github/copilot-instructions.md` - Updated for separate repo pattern

### New Files
- `example-config/` - Complete example configuration repository
  - `example-config/envs/` - Example environments (copied from original)
  - `example-config/secrets/` - Secrets directory structure
  - `example-config/.gitignore` - Config repo gitignore
  - `example-config/.envrc.local.example` - Environment template
  - `example-config/README.md` - Config repo documentation (350+ lines)
- `docs/separate-config-repo.md` - Comprehensive guide (500+ lines)
- `ci/separate-config-ci.md` - CI/CD integration guide

## Benefits Summary

### For Framework Developers
- Focus on core functionality
- No need to maintain example configs
- Easier to version and release
- Clear separation of concerns

### For Infrastructure Operators
- Private configs in separate repo
- Independent versioning
- Easier team collaboration
- Better access control
- Can use same framework for multiple projects

### For Organizations
- Single framework, multiple config repos
- Per-project or per-client repos
- Easier auditing and compliance
- Better secret management
- Clearer ownership and responsibilities

## Support

- See `docs/separate-config-repo.md` for detailed guide
- Check `example-config/README.md` for config repo setup
- Review `ci/separate-config-ci.md` for CI/CD patterns
- Embedded config pattern still supported (no migration required)
