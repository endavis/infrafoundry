# 6. Packages as Primary Resource Model

**Date:** 2026-03-14
**Status:** Accepted (revised)
**Issue:** [#357](https://github.com/endavis/infrafoundry/issues/357)

## Context

Infrastructure packages (`infrafoundry.yml` manifest) proved to be a better resource model during the ONTAP cluster migration (#346). Packages provide self-contained, templated resource bundles with variables, event handlers, and clear boundaries. However, the current model treats packages as an optional feature nested under provider directories, and loose YAML resource files remain the default.

This creates several issues:

- **Fragmented config:** Related resources are spread across multiple loose YAML files with no grouping mechanism.
- **No templating for loose resources:** Only packages support Jinja2 variable substitution.
- **No targeting:** No way to apply/destroy a logical group of resources as a unit.

## Decision

We will promote packages to the primary resource model:

1. Add a `provider` field to `PackageManifest` for env-root packages.
2. Support package discovery at the environment root (`envs/{env}/`), not just under provider directories.
3. Skip directories containing `infrafoundry.yml` during provider discovery to avoid treating env-root packages as providers.
4. Emit deprecation warnings when loose resources (not in packages) are found.
5. Add `--package` / `-p` CLI flag for `plan`/`apply`/`destroy` to target specific packages.
6. Add `resolve_package_filter()` for CLI integration.
7. Add `PackageNotFoundError` exception for package resolution errors.
8. Decrypt SOPS-encrypted `settings.yaml` before generating terraform tfvars.

### Env-root packages

Packages at the environment root (`envs/{env}/{package-name}/infrafoundry.yml`) must declare a `provider` field since there is no parent provider directory to infer from. Provider-scoped packages (`envs/{env}/{provider}/{package-name}/`) can optionally declare `provider` to override the directory-inferred value.

### Shared per-provider terraform state

Packages use the existing shared per-provider terraform state model. The `--package` flag resolves the package's resource names and passes them as `-target` flags to terraform, ensuring only the targeted resources are affected.

### Per-package state isolation — attempted and reverted

Per-package terraform state isolation (each package gets its own terraform directory and state file) was implemented in PRs #374, #381, #382, #383 and subsequently reverted. The approach required an escalating series of fixes to handle multi-provider packages in a single terraform directory:

- **Provider file namespacing** (PR #381): Each provider's `provider.tf`, `variables.tf`, `outputs.tf`, and `terraform.tfvars` had to be namespaced (e.g., `provider_proxmox.tf`, `provider_opnsense.tf`) to avoid overwriting when multiple providers shared a package directory.
- **Required providers merging** (PR #382): Terraform only allows one `terraform { required_providers {} }` block per module. A post-processing step was needed to extract and merge provider declarations from each namespaced file into a shared `required_providers.tf`.
- **Lock file upgrading** (PR #383): The first provider to run `terraform init` created a lock file without the second provider's entries. Detection logic was added to check the lock file against `required_providers.tf` and re-run `init -upgrade`.
- **Stale file cleanup** (PR #381): The existing `.tf` file cleanup had to be made provider-aware to avoid one provider's cleanup removing another provider's resource files from the shared directory.
- **tfvars auto-loading** (PR #383): Namespaced tfvars (`terraform_proxmox.tfvars`) weren't auto-loaded by terraform, requiring a rename to `*.auto.tfvars`.

More critically, **cross-package terraform references broke entirely**. For example, DHCP reservations in the ONTAP cluster package referenced `opnsense_kea_subnet.opt1_infrastructure.id` — a subnet resource managed in a separate kea-dhcp package's terraform state. This fundamental limitation meant packages could not be truly self-contained: any resource referencing something in another package required custom data source integration or manual ID lookup.

The shared per-provider state model avoids all of these issues. All opnsense resources (subnets and reservations) share one terraform state, so cross-resource references work naturally. The `--package` flag with `-target` filtering provides the scoped operations users need without state isolation overhead.

### Loose resource deprecation

Loose YAML resources (not inside a package directory) will:
- Continue to work but emit a `DeprecationWarning`
- Be phased out in a future release
- Users should migrate them to packages with an `infrafoundry.yml` manifest

## Consequences

**Positive:**

- **Clear boundaries:** Each package is a self-contained unit with explicit inputs (variables) and outputs (resources).
- **Env-root placement:** Packages at the environment root are provider-agnostic, enabling multi-provider packages.
- **Targeted operations:** `--package` flag scopes plan/apply/destroy to a package's resources.
- **Cross-resource references:** Shared per-provider state means terraform references between resources (even across packages) work naturally.
- **Gradual migration:** Loose resources continue to work with deprecation warnings, giving users time to migrate.

**Negative:**

- **No state isolation:** Applying a package still loads all provider resources into terraform state. The `-target` flag limits what terraform touches, but drift detection sees everything.
- **Migration effort:** Existing environments with loose resources need to be restructured into packages.
- **Provider field requirement:** Env-root packages must explicitly declare their provider.

## Alternatives Considered

1. **Per-package terraform state isolation:** Attempted and reverted (see above). Too many band-aids required for multi-provider packages and cross-package references.

2. **Keep packages as optional feature:** Rejected because loose resources lack templating, isolation, and grouping. Packages are strictly better.

3. **Remove loose resources immediately:** Rejected because it would be a breaking change with no migration path. Deprecation warnings give users time to adopt packages.

4. **Infer provider for env-root packages from resource content:** Rejected because resources may span multiple providers, and the manifest `provider` field serves as the default/primary provider for the package.

## Documentation

- [Infrastructure Packages](../../configuration/infrastructure-packages.md)
