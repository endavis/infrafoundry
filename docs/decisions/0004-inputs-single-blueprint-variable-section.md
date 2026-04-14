# ADR-0004: Use `inputs:` as the single blueprint variable declaration section

## Status

Accepted

Related issue: [#607](https://github.com/endavis/infrafoundry/issues/607)

## Context

`foundry config doctor --deep` reported 33 errors across the five in-repo
blueprints because the validator treats every template variable that is not
present in `defaults:` as undefined. In practice, most of those 33 variables
are legitimate per-instance inputs supplied by the package (VM names, VM IDs,
target nodes, IP addresses, DHCP subnets, etc.), not typos. The old schema
had no way for a blueprint author to say "this variable is a required input
the package must supply" — the only mechanism was `defaults:`, which
conflates "optional input with a fallback value" and "variable declaration"
into a single construct.

The consequences were:

1. Every blueprint produced a wall of noise under `config doctor`, drowning
   out real mistakes (typos, missing inputs) that the check is supposed to
   catch.
2. Blueprint authors had no vocabulary for required-input semantics, so
   there was no self-documenting place for package authors to look when
   wiring up a new blueprint.
3. Tooling that wants to surface "what must I supply?" has nothing to read.

InfraFoundry is still pre-release with no external blueprint authors, so a
clean schema change is the right moment to fix this before the surface
solidifies.

## Decision

`inputs:` replaces `defaults:` as the single variable-declaration section in
blueprint manifests.

**Schema (3C — unified inputs):**

- A blueprint's variables are declared in an `inputs:` list.
- Each entry is a mapping with at least a `name`, plus optional
  `description`, `type`, and `default`.
- Presence of `default:` marks the input as optional; absence marks it as
  required.
- Declaring both `inputs:` and the legacy `defaults:` in the same scope is
  a hard error at resolve time. No dual-schema support.

**Scoping (5Y — top-level plus per-provider):**

- A top-level `inputs:` list applies to every provider in a multi-provider
  blueprint. Top-level required inputs must always be supplied.
- Inside each entry under `providers:`, a nested `inputs:` list declares
  inputs that are only in scope when that provider's templates render.
  Provider-scoped required inputs are only mandatory when that provider is
  instantiated.
- The validator checks each provider against the union of top-level ∪
  provider-scoped input names.

**Implementation contract:**

- `BlueprintResolver.resolve` parses `inputs:` into an ordered list and
  synthesises a legacy-shape `defaults` dict (containing only inputs that
  carry `default:`) so `package_loader.py` consumers of `blueprint["defaults"]`
  continue working unchanged. The merge order
  `blueprint.defaults < providers[x].defaults < package.variables`
  is preserved exactly.
- The resolver also populates `input_names: frozenset[str]` at the
  top level and inside each provider block.
- `BlueprintValidator` checks template variables against `input_names`
  (falling back to `defaults.keys()` for legacy test fixtures that build
  resolved dicts by hand), and reports `"Undefined variable: 'foo' (not
  declared in inputs)"` when a reference has no matching declaration.

## Consequences

**Easier:**

- `config doctor --deep` now gives actionable signal: a reported undefined
  variable is always a real bug (typo or missing input declaration), not
  noise.
- Blueprint authors have a single, self-documenting place to describe every
  variable their blueprint consumes, including whether it is required.
- Package authors can see at a glance which variables they must supply by
  reading a blueprint's `inputs:` section.
- Future tooling (IDE autocomplete, `config schema`, interactive scaffolding)
  has a well-defined declaration surface to read.

**More difficult:**

- Every existing in-repo blueprint had to be migrated by hand (five
  manifests). For any future external blueprint authors, this is a
  backwards-incompatible schema change they must adopt — mitigated by the
  pre-release status.
- Blueprint authors must remember to add new inputs to `inputs:` when
  templates start referencing them. The validator error catches this
  immediately, but it is still one more thing to keep in sync.

**Neutral:**

- No runtime behaviour change for packages: the synthesised `defaults` dict
  preserves the existing merge contract.

## Implementation

- Resolver: `src/infrafoundry/core/config/blueprint_resolver.py`
- Validator: `src/infrafoundry/core/config/blueprint_validator.py`
- Migrated blueprints: `blueprints/{aiqum,k3s-cluster,ontap-cluster,rocky9-template,ubuntu-template}/blueprint.yaml`
- Tests: `tests/unit/test_blueprint_resolver.py`, `tests/unit/test_blueprint_validator.py`
- Documentation: [Configuration Blueprints Guide](../configuration/blueprints.md)
