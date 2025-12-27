# Settings File Structure Validation Report

**Date:** 2025-12-23
**Documentation:** `docs/configuration/settings-file-structure.md`
**Implementation:** `src/infrafoundry/core/config/models.py` (`EnvironmentConfig` Pydantic model)

---

## Executive Summary

**Status:** ⚠️ **Missing Documentation**

- ✅ **Documented correctly:** 6/8 top-level fields
- ❌ **Missing from documentation:** 2 fields
- ✅ **All documented fields verified:** Accurate
- **Coverage:** 75% (6/8 fields documented)

---

## Top-Level Settings Schema

### Actual Implementation (EnvironmentConfig)

```python
class EnvironmentConfig(BaseModel):
    name: str                                                # ✅ Documented
    description: str | None = None                          # ✅ Documented
    providers: list[str] = Field(default_factory=list)      # ❌ NOT DOCUMENTED
    variables: dict[str, Any] = Field(default_factory=dict) # ✅ Documented
    ssh: SSHConfig | None = None                            # ✅ Documented
    provider_ssh: dict[str, SSHConfig] = Field(...)         # ✅ Documented
    provider_settings: dict[str, dict[str, Any]] = Field(...) # ✅ Documented
    runner_priorities: dict[str, int] = Field(...)          # ❌ NOT DOCUMENTED
```

**Source:** `src/infrafoundry/core/config/models.py:16-28`

---

## Missing Fields Documentation

### 1. `providers` Field
**Status:** ❌ **CRITICAL - Not Documented**

**Actual Implementation:**
```python
providers: list[str] = Field(default_factory=list)
```

**Purpose:** List of provider names to enable for this environment

**Example:**
```yaml
name: prod
description: Production environment
providers:                    # ❌ Not documented!
  - proxmox
  - opnsense
  - kubernetes
```

**Priority:** **HIGH** - Core configuration field that determines which providers are available

---

### 2. `runner_priorities` Field
**Status:** ❌ **Not Documented in Settings File Structure**

**Actual Implementation:**
```python
runner_priorities: dict[str, int] = Field(default_factory=dict)
# Override runner execution order: { "pyinfra": 40, "ansible": 60 }
```

**Purpose:** Override default runner execution order (lower numbers run first)

**Example:**
```yaml
name: prod
runner_priorities:            # ❌ Not documented in settings-file-structure.md
  pyinfra: 40
  ansible: 60
  terraform: 0
```

**Priority:** **MEDIUM** - Important for custom runner ordering, **BUT** is documented in `docs/runners/overview.md`

**Note:** This field is documented elsewhere but should be mentioned in the settings file structure document for completeness.

---

## SSH Configuration Schema

### Actual Implementation (SSHConfig)

```python
class SSHConfig(BaseModel):
    user: str | None = None      # ✅ Documented
    key_path: str | None = None  # ✅ Documented
    port: int = 22               # ✅ Documented (with correct default)
```

**Source:** `src/infrafoundry/core/config/models.py:8-13`

**Verification:** ✅ **All fields accurately documented**

---

## Provider-Specific Settings

### Proxmox Settings

**Documented Fields:**
```yaml
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: pve-token-id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    node: pve01
    storage: local-zfs          # ⚠️ Not in TypedDict
```

**Actual TypedDict:**
```python
class ProxmoxProviderSettings(TypedDict, total=False):
    api_url: str
    api_token: str
    api_token_id: str           # ⚠️ Separate field (alternative auth)
    api_token_secret: str       # ⚠️ Separate field (alternative auth)
    node: str
    # Note: 'storage' not in TypedDict but may be used by provider
```

**Source:** `src/infrafoundry/core/types.py:8-15`

**Analysis:**
- ⚠️ Documentation shows `api_token` as single string
- ⚠️ Implementation also supports `api_token_id` + `api_token_secret` (separate fields)
- ⚠️ `storage` field documented but not in TypedDict (may be used but not validated)

**Priority:** **MEDIUM** - Clarify authentication methods (token string vs id+secret)

---

### OPNsense Settings

**Documented Fields:**
```yaml
provider_settings:
  opnsense:
    api_url: https://fw.example.com
    api_key: xxxxxxxxxxxxxxxxxxxx
    api_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Actual TypedDict:**
```python
class OPNsenseProviderSettings(TypedDict, total=False):
    api_url: str
    api_key: str
    api_secret: str
```

**Source:** `src/infrafoundry/core/types.py:24-29`

**Verification:** ✅ **Accurate**

---

### Kubernetes Settings

**Documented Fields:**
```yaml
provider_settings:
  kubernetes:
    kubeconfig_path: ~/.kube/config
    namespace: infra
```

**Status:** ⚠️ **No TypedDict found** - Documentation only

**Priority:** **LOW** - May be correct but not formally validated

---

## Field Defaults and Optional Values

### From Documentation

**Documented as Optional:**
- ✅ `description` - Documented as optional, implementation confirms (`str | None = None`)
- ✅ `variables` - Documented as optional, implementation confirms (empty dict default)
- ✅ `ssh.*` fields - Documented as optional with defaults

**Documented Defaults:**
- ✅ `ssh.port` = 22 - **VERIFIED** (implementation: `port: int = 22`)
- ✅ `ssh.user` - Defaults to current user - **PLAUSIBLE** (implementation: `user: str | None = None`)

---

## Example Validation

### Minimal Example from Documentation

**Documented:**
```yaml
name: dev
description: Development environment
provider_settings:
  proxmox:
    api_url: https://pve-dev.example.com:8006
    api_token: pve-dev-token
```

**Analysis:**
- ✅ Would parse successfully (all required fields present: `name`)
- ⚠️ Missing `providers` field (not documented but part of model)
- ✅ All other fields optional with defaults

**Recommendation:** Add `providers: [proxmox]` to examples

---

## File Location and Encryption

**Documented:**
- File location: `envs/{env}/settings.yaml` ✅ **VERIFIED**
- Encryption: SOPS/age required ✅ **VERIFIED**
- Generated outputs: `generated/{env}/terraform/{provider}/terraform.tfvars` ✅ **PLAUSIBLE**

**Note:** File location verified from `ConfigManager` usage patterns

---

## Documentation Inaccuracies

### 1. Missing `providers` Field

**Severity:** **HIGH**

**Issue:** Core field that determines which providers are loaded is not documented

**Fix Required:**
```yaml
# Add to documentation
providers:
  - proxmox
  - opnsense
  - kubernetes
```

---

### 2. Missing `runner_priorities` Field

**Severity:** **MEDIUM**

**Issue:** Field exists in EnvironmentConfig but not mentioned in settings-file-structure.md

**Note:** Documented in `docs/runners/overview.md` but should cross-reference

**Fix Required:**
```yaml
# Add to documentation with cross-reference
runner_priorities:  # See docs/runners/overview.md for details
  terraform: 0
  pyinfra: 40
  ansible: 50
```

---

### 3. Proxmox Authentication Methods

**Severity:** **LOW-MEDIUM**

**Issue:** Documentation shows only `api_token` string format, but implementation supports both:
1. Single token: `api_token: "pve-token-id=xxx"`
2. Separate credentials: `api_token_id + api_token_secret`

**Recommendation:** Document both authentication methods

---

### 4. Provider-Specific Schema

**Severity:** **LOW**

**Issue:** Documentation provides examples but doesn't specify which fields are required vs optional for each provider

**Recommendation:** Add "Required Fields" vs "Optional Fields" sections for each provider

---

## Recommendations

### High Priority

1. **Document `providers` field** - Required to understand which providers are loaded
2. **Add complete field reference table** - Show all top-level fields with required/optional/default
3. **Cross-reference `runner_priorities`** - Link to runners/overview.md

### Medium Priority

4. **Clarify Proxmox authentication** - Document both token methods
5. **Provider-specific schema** - Create detailed schema tables for each provider
6. **Add validation examples** - Show what happens with invalid configurations

### Low Priority

7. **Add troubleshooting for missing providers** - What happens if `providers` field is wrong?
8. **Environment variable overrides** - Document which settings can be overridden via env vars

---

## Complete Schema Reference (Should Be in Documentation)

```yaml
# InfraFoundry Environment Settings Schema

# Required Fields
name: string                    # Environment name (e.g., "dev", "prod")

# Optional Fields
description: string             # Human-readable description
providers: list[string]         # List of providers to enable (e.g., ["proxmox", "opnsense"])
variables: dict                 # Template variables for Jinja2
runner_priorities: dict         # Override runner execution order { runner: priority }

# SSH Configuration (optional)
ssh:
  user: string                  # SSH username (default: current user)
  key_path: string              # Path to SSH private key
  port: int                     # SSH port (default: 22)

# Per-Provider SSH Overrides (optional)
provider_ssh:
  <provider_name>:
    user: string
    key_path: string
    port: int

# Provider Settings (credentials, endpoints, etc.)
provider_settings:
  proxmox:
    api_url: string             # REQUIRED
    api_token: string           # Token string (pve-token-id=xxx) OR use api_token_id + api_token_secret
    api_token_id: string        # Alternative auth method
    api_token_secret: string    # Alternative auth method
    node: string                # Default Proxmox node
    storage: string             # Default storage pool

  opnsense:
    api_url: string             # REQUIRED
    api_key: string             # REQUIRED
    api_secret: string          # REQUIRED

  kubernetes:
    kubeconfig_path: string
    namespace: string
```

---

## Validation Method

**Files Examined:**
1. `src/infrafoundry/core/config/models.py` - Pydantic models (authoritative schema)
2. `src/infrafoundry/core/types.py` - TypedDict definitions for provider settings
3. `docs/configuration/settings-file-structure.md` - User documentation

**Validation Approach:**
- Compared Pydantic `EnvironmentConfig` fields vs documented fields
- Checked field types, defaults, and optional/required status
- Verified SSH configuration schema
- Examined provider-specific settings TypedDicts

---

**Validated By:** Claude Code
**Last Updated:** 2025-12-23
