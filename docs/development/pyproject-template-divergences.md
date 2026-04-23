# pyproject-template Divergences

InfraFoundry was bootstrapped from [pyproject-template](https://github.com/endavis/pyproject-template)
and periodically syncs from it. This document codifies the files InfraFoundry
intentionally does **not** adopt from upstream, so every sync PR does not
re-litigate the same decisions.

## When to consult this document

- **Reviewing a sync PR** (typically titled `chore: sync from pyproject-template …`):
  use the categories below to decide whether a changed file should be adopted
  verbatim, skipped, or hand-merged.
- **Proposing upstream changes**: if a divergence is permanent, record it here
  rather than in a PR comment that gets lost in history.

## How to update this document

Edit it in a **separate PR** with a `docs:` commit. Do not silently expand the
skip-list inside a sync PR — that hides the decision. The divergence list is a
deliberate policy artifact; additions deserve review on their own merits.

A programmatic skip-list in `.config/pyproject_template/settings.toml` is a
future improvement that would let tooling enforce these decisions. Until that
lands, this doc is the MVP — a human reference consulted during sync-PR review.

> **Scope note:** by omission, every file not mentioned in one of the three
> categories below is adopted verbatim from upstream. There is no explicit
> "adopt" list — keeping the doc small is the point.

## 1. Template-skeleton files (never adopt)

These files exist upstream as part of the generic skeleton a new project would
start from. InfraFoundry is a real project with its own package structure,
tests, and documentation; upstream changes to these files should always be
skipped.

### Skeleton source code
- `src/package_name/` — skeleton package. InfraFoundry's package lives at
  `src/infrafoundry/`.
- `examples/api/` — skeleton FastAPI example.
- `examples/basic_usage.py`, `examples/advanced_usage.py`,
  `examples/cli_usage.py` — skeleton usage examples. InfraFoundry ships
  `blueprints/` instead.

### Skeleton tests
- `tests/test_cli.py`, `tests/test_core.py`, `tests/test_logging.py`,
  `tests/test_example.py` — skeleton tests for the placeholder package.
- `tests/benchmarks/test_bench_core.py`,
  `tests/benchmarks/test_bench_logging.py` — benchmarks for the skeleton
  package.
- `tests/template/` — tests upstream runs against the template itself (bootstrap,
  cleanup, doit helpers). Not relevant once bootstrapped.

### Skeleton documentation
- `docs/examples/api.md`, `docs/examples/add-a-feature.md` — skeleton example
  docs.
- `docs/usage/basics.md`, `docs/usage/cli.md` — skeleton usage docs. Superseded
  by InfraFoundry's `docs/usage/`.
- `docs/reference/api.md` — auto-generated API reference for the skeleton
  package.
- `docs/template/` — upstream documentation about the template project itself
  (bootstrap, migration, updates).
- `docs/deployment/development.md`, `docs/deployment/production.md` — generic
  deployment docs that do not apply to an infrastructure tool.
- `docs/getting-started/installation.md` — generic install doc. InfraFoundry's
  `docs/getting-started/setup-guide.md` is the real entry point.
- `docs/development/extensions.md`,
  `docs/development/install-tools-framework.md`,
  `docs/development/tooling-roles.md`,
  `docs/development/github-repository-settings.md`,
  `docs/development/dependabot-automerge.md` — skeleton/meta docs about the
  template's own tooling choices.
- `docs/TABLE_OF_CONTENTS.md` — skeleton table of contents. Superseded by the
  mkdocs-generated nav.

### Other
- `LICENSE` — InfraFoundry ships its own license; never overwrite.

## 2. Infrafoundry-specific files (upstream changes never apply)

These files exist only in InfraFoundry. They are listed here so reviewers know
not to ask "should we sync this?" — there is nothing to sync from.

- `src/infrafoundry/` — the actual framework code.
- `blueprints/` — infrastructure blueprints.
- `tools/lint_blueprint_portability.py` — custom linter enforcing the
  blueprint-script portability contract.
- `docs/development/blueprint-script-portability.md` — the contract the linter
  enforces.
- `docs/development/implementing-providers.md`,
  `docs/development/implementing-runners.md`,
  `docs/development/implementing-secret-providers.md`,
  `docs/development/manager-patterns.md`,
  `docs/development/event-system.md`,
  `docs/development/credential-loader-system.md`,
  `docs/development/runner-protocol-quick-reference.md` — framework-specific
  developer guides.
- InfraFoundry-authored ADRs under `docs/decisions/` and
  `docs/architecture/decisions/` (files numbered `0001–0006` in each tree).
  Upstream ships its own ADRs in the `9000-` series; those are adopted
  separately.

Note: `tools/doit/quality.py` is an upstream file but contains an
infrafoundry-specific task (`task_lint_blueprints()`). See category 3.

## 3. Files that require hand-merge every sync

These files mix upstream skeleton content with InfraFoundry customization. They
cannot be adopted blindly and cannot be skipped blindly — each sync must
manually reconcile the two. For each, the "spot-check" column names the
customization a reviewer must verify survived the merge.

| File | Spot-check |
| :--- | :--- |
| `AGENTS.md` | Preserves InfraFoundry-specific CLI command tables, architecture sections, and the `foundry` CLI reference. |
| `.claude/CLAUDE.md` | Preserves InfraFoundry TodoWrite rules, workflow mandates, and the `@../AGENTS.md` import. |
| `.claude/settings.json` | Preserves project-specific permissions, hooks, and environment variables. |
| `.github/CONTRIBUTING.md` | Preserves InfraFoundry branching/commit conventions and the issue-driven workflow description. |
| `.gitignore` | Preserves entries for `generated/`, state DB paths, `endavis-infra/`, and other InfraFoundry-specific artifacts. |
| `.envrc` | Preserves `INFRAFOUNDRY_*` environment variables and direnv layout specific to the framework. |
| `.pre-commit-config.yaml` | Preserves InfraFoundry-specific hooks (blueprint linter, commit-msg format) alongside upstream quality hooks. |
| `CHANGELOG.md` | InfraFoundry owns this — never replaced, only appended. |
| `README.md` | Preserves InfraFoundry description, quickstart, and feature list. |
| `dodo.py` | Preserves InfraFoundry-specific task imports. |
| `mkdocs.yml` | Preserves the InfraFoundry nav tree (Providers, Runners, Configuration, etc.). |
| `pyproject.toml` | Preserves project name, dependencies, CLI entry points, and mypy/ruff overrides specific to InfraFoundry. |
| `tools/doit/quality.py` | Preserves `task_lint_blueprints()` and any sibling blueprint-specific tasks. |

When reviewing a sync PR that touches any of the above, scroll through the diff
with the spot-check note in mind. If the customization is missing from the
proposed change, the merge lost it — push back and ask for a rework.

## 4. Temporarily deferred files

Unlike the categories above, these files **will** be adopted — just not in the
current sync phase. They are listed here so a reviewer opening this doc after
Phase A does not assume they were skipped permanently. Remove each entry once
the referenced follow-up phase lands.

- `.github/workflows/ci-full-matrix.yml` and
  `tests/test_ci_full_matrix_workflow.py` — deferred from Phase A to Phase E
  of sync tracker #673. Upstream `ci-full-matrix.yml` calls
  `./.github/workflows/ci.yml` with `with: full_matrix: true`, but our
  `ci.yml` does not declare that `workflow_call` input. Phase E will add the
  input (and switch the label-check logic to read from it), at which point
  these two files can be adopted verbatim. Remove this note once Phase E
  lands.
