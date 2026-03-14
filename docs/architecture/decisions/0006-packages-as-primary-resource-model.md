# 6. Packages as Primary Resource Model

**Date:** 2026-03-14
**Status:** Accepted
**Issue:** [#357](https://github.com/endavis/infrafoundry/issues/357)

## Context

Infrastructure packages (`infrafoundry.yml` manifest) proved to be a better resource model during the ONTAP cluster migration (#346). Packages provide self-contained, templated resource bundles with variables, event handlers, and clear boundaries. However, the current model treats packages as an optional feature nested under provider directories, and loose YAML resource files remain the default.

This creates several issues:

- **No isolation:** All resources for a provider share one terraform directory and state file, making targeted operations risky.
- **No portability:** Resources can't be easily moved, backed up, or managed independently.
- **Fragmented config:** Related resources are spread across multiple loose YAML files with no grouping mechanism.
- **No templating for loose resources:** Only packages support Jinja2 variable substitution.

## Decision

We will promote packages to the primary resource model in three phases:

### Phase 1 (this ADR)
1. Add a `provider` field to `PackageManifest` for env-root packages.
2. Support package discovery at the environment root (`envs/{env}/`), not just under provider directories.
3. Skip directories containing `infrafoundry.yml` during provider discovery to avoid treating env-root packages as providers.
4. Emit deprecation warnings when loose resources (not in packages) are found.
5. Add `PackageNotFoundError` exception for package resolution errors.

### Phase 2 (future)
- Per-package terraform state isolation: each package gets its own terraform working directory and state file.

### Phase 3 (future)
- `--package` / `-p` CLI flag for `plan`/`apply`/`destroy` to target specific packages.
- `resolve_package_filter()` for CLI integration.

### Env-root packages

Packages at the environment root (`envs/{env}/{package-name}/infrafoundry.yml`) must declare a `provider` field since there is no parent provider directory to infer from. Provider-scoped packages (`envs/{env}/{provider}/{package-name}/`) can optionally declare `provider` to override the directory-inferred value.

### Loose resource deprecation

Loose YAML resources (not inside a package directory) will:
- Continue to work but emit a `DeprecationWarning`
- Be phased out in a future release
- Users should migrate them to packages with an `infrafoundry.yml` manifest

## Consequences

**Positive:**

- **Clear boundaries:** Each package is a self-contained unit with explicit inputs (variables) and outputs (resources).
- **Env-root placement:** Packages at the environment root are provider-agnostic, enabling multi-provider packages.
- **Gradual migration:** Loose resources continue to work with deprecation warnings, giving users time to migrate.
- **Foundation for isolation:** The `provider` field and env-root discovery lay the groundwork for per-package terraform state in Phase 2.

**Negative:**

- **Migration effort:** Existing environments with loose resources need to be restructured into packages.
- **Provider field requirement:** Env-root packages must explicitly declare their provider, adding a mandatory field.
- **Discovery complexity:** Provider discovery must now skip directories containing `infrafoundry.yml`.

## Alternatives Considered

1. **Keep packages as optional feature:** Rejected because loose resources lack templating, isolation, and grouping. Packages are strictly better.

2. **Remove loose resources immediately:** Rejected because it would be a breaking change with no migration path. Deprecation warnings give users time to adopt packages.

3. **Infer provider for env-root packages from resource content:** Rejected because resources may span multiple providers, and the manifest `provider` field serves as the default/primary provider for the package.

## Documentation

- [Infrastructure Packages](../../configuration/infrastructure-packages.md)
