## Mypy Ignore Comments Found in Codebase

The following locations contain `# type: ignore` comments, indicating that `mypy` type checking is being bypassed for specific lines or files. These may represent areas where type annotations are incomplete, complex, or intentionally circumvented. Reviewing and potentially resolving these ignores can improve code clarity and type safety.

1.  **`src/infrafoundry/providers/opnsense/components/isc_to_kea_migration.py:328`**
    ```python
    isc_service: ISCDHCPService = ISCDHCPService.from_environment(  # type: ignore[assignment]
    ```
    *   **Reason for ignore:** `ignore[assignment]` suggests a potential type mismatch during assignment that `mypy` could not resolve, possibly due to dynamic assignment or complex return types.

2.  **`src/infrafoundry/providers/opnsense/components/kea_dhcp.py:24`**
    ```python
    service: KeaDHCPService = KeaDHCPService.from_environment(  # type: ignore[assignment]
    ```
    *   **Reason for ignore:** Similar to the above, `ignore[assignment]` points to a type issue during object assignment.

3.  **`src/infrafoundry/providers/opnsense/components/kea_dhcp.py:47`**
    ```python
    service: KeaDHCPService = KeaDHCPService.from_environment(  # type: ignore[assignment]
    ```
    *   **Reason for ignore:** Another `ignore[assignment]` for `KeaDHCPService.from_environment`.

4.  **`src/infrafoundry/providers/opnsense/components/kea_dhcp.py:83`**
    ```python
    service: KeaDHCPService = KeaDHCPService.from_environment(  # type: ignore[assignment]
    ```
    *   **Reason for ignore:** Yet another `ignore[assignment]` for `KeaDHCPService.from_environment`.

5.  **`src/infrafoundry/core/runners/runner_registry.py:29`**
    ```python
            tool_name = runner_class._tool_name  # type: ignore
    ```
    *   **Reason for ignore:** General `type: ignore` suggests that `runner_class` might not be consistently typed to have `_tool_name`, or `mypy` cannot infer this attribute correctly due to dynamic access patterns or mixin usage.

6.  **`src/infrafoundry/core/provider.py:15`**
    ```python
    ValidationReport = None  # type: ignore
    ```
    *   **Reason for ignore:** General `type: ignore` here is used because `ValidationReport` is conditionally imported. If the import fails, it's set to `None`, which `mypy` would flag as a type mismatch if `ValidationReport` is later expected to be a type.

---

## Configuration-Level Ignores (pyproject.toml)

### Ruff Ignores (lines 53-64)

**Annotation Rules (marked "fix incrementally"):**
- `ANN401` - Dynamically typed expressions (Any)
- `ANN001` - Missing type annotation for function argument
- `ANN002` - Missing type annotation for *args
- `ANN003` - Missing type annotation for **kwargs
- `ANN201` - Missing return type annotation for public function
- `ANN202` - Missing return type annotation for private function

**Other Rules:**
- `B024` - Abstract base class without abstract methods (intentional, keep)
- `B904` - raise-without-from (fix incrementally)
- `RUF012` - Mutable class default (fix incrementally)
- `E402` - Module level import not at top (needed for CLI, keep)

### Mypy Config (line 77)
- `disallow_any_generics = false` - Allows generic types without type parameters (can enable later)

---

## Action Plan - Fix Ignores Incrementally

### Priority 1: Fix In-Code Type Ignores (6 instances) ✅ COMPLETED
- [x] **runner_registry.py:29** - Add proper typing for `_tool_name` attribute
  - Fixed by using `getattr(runner_class, "_tool_name", None)` instead of direct attribute access
- [x] **provider.py:15** - Use proper Optional typing for conditional import
  - Removed try/except fallback, imported `ValidationReport` directly
  - Updated method signatures to use `ValidationReport` instead of `Any`
- [x] **OPNsense services (4 instances)** - Fix `from_environment()` return type signatures
  - Updated `BaseService.from_environment()` to return `Self` instead of `"BaseService"`
  - Removed all `# type: ignore[assignment]` comments from ISC/Kea DHCP components

**Result:** All 6 in-code `# type: ignore` comments have been removed! ✅

### Priority 2: Enable Strict Ruff Annotation Rules
Once in-code ignores are fixed, incrementally enable these rules by removing from pyproject.toml:
- [ ] `ANN201` - Return type annotations for public functions
- [ ] `ANN202` - Return type annotations for private functions
- [ ] `ANN001` - Function argument annotations
- [ ] `ANN401` - Remove usage of bare `Any` types

### Priority 3: Fix Other Ruff Rules
- [ ] `B904` - Add proper exception chaining with `raise ... from ...`
- [ ] `RUF012` - Fix mutable class defaults

### Priority 4: Enable Strict Mypy Generics
- [ ] Set `disallow_any_generics = true` once all generic types are properly parameterized

**Rules to Keep:**
- `B024` - Abstract base class pattern is intentional
- `E402` - CLI command loading requires deferred imports

---

## Current Status (2025-01-20)

### Completed ✅
- **All 6 in-code `# type: ignore` comments removed**
- All tests passing (459/459)
- Ruff linting passes
- Deprecated rules identified (ANN101, ANN102 no longer exist in ruff)

### Remaining Work
- **120 mypy type errors** across 40 files to address
  - Includes issues with: exception constructors, Any types, untyped functions, SQLAlchemy column types, etc.
  - These are pre-existing issues, not caused by the recent fixes
- Update `pyproject.toml` to remove deprecated ANN101/ANN102 rules
- Incrementally enable stricter annotation rules (Priority 2-4)
