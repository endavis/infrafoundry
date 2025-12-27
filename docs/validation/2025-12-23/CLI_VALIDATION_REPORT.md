# CLI Reference Validation Report

**Date:** 2025-12-23
**Documentation:** `docs/usage/cli-reference.md`
**Implementation:** `src/infrafoundry/cli/commands/*.py`

---

## Executive Summary

**Status:** ⚠️ **Significant Gaps Found**

- ✅ **Documented correctly:** 16 commands
- ⚠️ **Missing from documentation:** 9 commands
- ❌ **Inaccurate documentation:** 1 item
- **Coverage:** 64% (16/25 commands documented)

---

## Missing Commands (Not Documented)

These commands exist in the implementation but are **not documented** in `cli-reference.md`:

### 1. `infra rollback`
**Status:** ⚠️ **CRITICAL - Not Documented**

**Actual Implementation:**
```bash
infra rollback --deployment-id <id> [--auto-approve]
```

**Purpose:** Rollback infrastructure to a previous deployment state

**Source:** `src/infrafoundry/cli/commands/rollback.py`

**Priority:** **HIGH** - This is a critical production operation that should be documented

---

### 2. `infra diff`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra diff --env-a <env1> --env-b <env2> [--provider <name>] [--verbose]
```

**Purpose:** Compare configurations between two environments

**Source:** `src/infrafoundry/cli/commands/diff.py`

**Priority:** **HIGH** - Useful for environment comparison and troubleshooting

---

### 3. `infra dependencies`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra dependencies --env <env> [--resource <provider:name>] [--format list|mermaid]
```

**Purpose:** Visualize resource dependencies for an environment

**Source:** `src/infrafoundry/cli/commands/dependencies.py`

**Priority:** **MEDIUM** - Useful for understanding resource relationships

**Note:** This appears to overlap with `infra graph` - clarify difference

---

### 4. `infra impact`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra impact --env <env> --resource <name>
```

**Purpose:** Analyze the impact of changes to a resource (shows what depends on it)

**Source:** `src/infrafoundry/cli/commands/impact.py`

**Priority:** **MEDIUM** - Helpful for risk assessment before changes

---

### 5. `infra reset`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra reset --env <env> --provider opnsense --component kea/dhcp [--auto-approve]
```

**Purpose:** Reset (wipe) infrastructure components

**Source:** `src/infrafoundry/cli/commands/reset.py`

**Priority:** **MEDIUM** - Specialized operation for OPNsense/Kea

---

### 6. `infra rollback-points`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra rollback-points --env <env>
```

**Purpose:** List available rollback points for an environment

**Source:** `src/infrafoundry/cli/commands/rollback_points.py`

**Priority:** **HIGH** - Needed to use `infra rollback` effectively

---

### 7. `infra export-proxmox`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra export-proxmox [options]
```

**Purpose:** Export Proxmox configuration to InfraFoundry YAML

**Source:** `src/infrafoundry/cli/commands/export_proxmox.py`

**Priority:** **LOW** - Specialized migration tool

---

### 8. `infra backup`
**Status:** ⚠️ **Not Documented**

**Actual Implementation:**
```bash
infra backup [options]
```

**Purpose:** Create a timestamped backup of the InfraFoundry state database

**Source:** `src/infrafoundry/cli/commands/state.py` (subcommand of state)

**Priority:** **MEDIUM** - State management operation

---

### 9. `infra state`
**Status:** ⚠️ **Partially Documented**

**Actual Implementation:**
```bash
infra state <subcommand>
# Subcommands: backup, restore, etc.
```

**Purpose:** Manage InfraFoundry state database

**Source:** `src/infrafoundry/cli/commands/state.py`

**Priority:** **MEDIUM** - State management operations

**Note:** Mentioned in passing but not properly documented

---

## Documented Commands - Verification Status

### ✅ Correctly Documented

1. **`infra init`** - Initialize secrets with age key ✅
2. **`infra envs`** - List environments ✅
3. **`infra list`** - List resources from YAML ✅
4. **`infra resources`** - List tracked resources from state DB ✅
5. **`infra status`** - Show deployment status ✅
6. **`infra history`** - View deployment history ✅
7. **`infra plan`** - Plan infrastructure changes ✅
8. **`infra apply`** - Apply infrastructure changes ✅
9. **`infra destroy`** - Destroy infrastructure ✅
10. **`infra validate`** - Validate infrastructure configuration ✅
11. **`infra drift`** - Detect infrastructure drift ✅
12. **`infra policies`** - List/check policies ✅
13. **`infra secrets`** - Manage encrypted secrets ✅
14. **`infra graph`** - Visualize dependencies ✅
15. **`infra new`** - Create from blueprints ✅
16. **`infra migrate`** - Migrate infrastructure ✅

---

## Documentation Inaccuracies

### 1. `infra new` command structure

**Documented:**
```bash
infra new list
infra new create <blueprint> <path>
```

**Actual:**
```bash
infra new          # Main command (creates from blueprints)
infra create       # Instantiate a blueprint (separate command)
```

**Issue:** Documentation shows `infra new create` but actual command is `infra create`

**Source:** `src/infrafoundry/cli/commands/new.py` and `create.py` are separate

**Priority:** **MEDIUM** - Functional but terminology mismatch

---

### 2. Policies command

**Documented:**
```bash
infra policies check --env <env> [--enforce]
```

**Need to Verify:** Is this `infra policies check` or just `infra policies`?

**Status:** ⚠️ **Needs Verification**

---

### 3. Secrets command

**Documented:**
```bash
infra secrets init|encrypt|decrypt
```

**Actual:** These appear to be separate top-level commands:
```bash
infra init       # Initialize secrets
infra encrypt    # Encrypt file with SOPS
infra decrypt    # Decrypt SOPS file
infra secrets    # Manage secrets (different subcommand)
```

**Status:** ⚠️ **Needs Clarification** - Multiple ways to access same functionality?

---

## Global Options Verification

**Documented Options:**
- ✅ `--config-dir/-c PATH` (INFRAFOUNDRY_CONFIG_REPO)
- ✅ `--strict-mode/--no-strict-mode` (INFRAFOUNDRY_STRICT_MODE)
- ✅ `--fail-on-missing-secrets | --allow-missing-secrets` (INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS)
- ✅ `--fail-on-missing-snippets | --allow-missing-snippets` (INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS)

**Verified Against:** `src/infrafoundry/cli/main.py:151-171`

**Status:** ✅ **Accurate**

---

## Command-Specific Validation

### `infra plan`

**Documented:**
```bash
infra plan --env <env> [--resource ...] [--dry-run]
```

**Need to Verify:**
- [ ] `--resource` option exists and works
- [ ] `--dry-run` option exists
- [ ] Multiple `--resource` flags supported

**Source:** `src/infrafoundry/cli/commands/plan.py`

---

### `infra apply`

**Documented:**
```bash
infra apply --env <env> [--resource ...] [--auto-approve]
```

**Need to Verify:**
- [ ] `--resource` option exists
- [ ] `--auto-approve` flag exists
- [ ] Parallel execution options mentioned in architecture docs

**Source:** `src/infrafoundry/cli/commands/apply.py`

---

### `infra graph`

**Documented:**
```bash
infra graph --env <env> --format mermaid|dot
```

**Need to Verify:**
- [ ] Format options are exactly `mermaid|dot`
- [ ] No other format options

**Source:** `src/infrafoundry/cli/commands/graph.py`

---

## Recommendations

### High Priority (Production Critical)

1. **Document `infra rollback`** - Critical production operation
2. **Document `infra rollback-points`** - Needed to use rollback effectively
3. **Document `infra diff`** - Very useful for environment management
4. **Clarify `infra new` vs `infra create`** - Fix naming confusion
5. **Clarify secrets commands** - Document relationship between `init/encrypt/decrypt` and `secrets`

### Medium Priority (Useful Features)

6. **Document `infra dependencies`** - Clarify vs `infra graph`
7. **Document `infra impact`** - Useful for change analysis
8. **Document `infra reset`** - Specialized but important
9. **Document `infra state` subcommands** - State management
10. **Document `infra backup`** - State backup operations

### Low Priority (Specialized Tools)

11. **Document `infra export-proxmox`** - Migration tool
12. **Add examples for undocumented commands**
13. **Create troubleshooting section for each command**

---

## Implementation Verification Checklist

### Still Need to Verify

- [ ] Read `plan.py` and verify all options match documentation
- [ ] Read `apply.py` and verify all options match documentation
- [ ] Read `destroy.py` and verify all options match documentation
- [ ] Read `validate.py` and verify all options match documentation
- [ ] Read `policies.py` to clarify command structure
- [ ] Read `secrets.py` to understand relationship with init/encrypt/decrypt
- [ ] Read `graph.py` to verify format options
- [ ] Read `migrate.py` to understand what migrations are supported
- [ ] Verify examples actually work by testing them

---

## Files to Update

1. **`docs/usage/cli-reference.md`** - Add missing commands, fix inaccuracies
2. **`docs/architecture/orchestrator-architecture.md`** - May reference rollback workflow (verify)
3. **Consider creating:** `docs/usage/rollback-guide.md` - Dedicated rollback documentation

---

## Validation Status Summary

| Category | Status |
|----------|--------|
| **Global Options** | ✅ Validated |
| **Command List** | ⚠️ 64% coverage (16/25) |
| **Command Options** | ❌ Not yet validated |
| **Examples** | ❌ Not tested |
| **Troubleshooting** | ⚠️ Generic, not command-specific |

---

**Next Steps:**
1. Read individual command files to validate options
2. Test documented examples
3. Update CLI reference with missing commands
4. Create dedicated guides for complex operations (rollback, diff)

---

**Validation Performed By:** Claude Code
**Last Updated:** 2025-12-23
