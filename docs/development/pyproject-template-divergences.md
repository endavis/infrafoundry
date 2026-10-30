---
title: "pyproject-template Divergences"
description: "Which template files InfraFoundry never adopts, owns, hand-merges or has deferred"
audience:
  - contributors
tags:
  - development
---

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

The programmatic skip-list lives at
`.config/pyproject_template/sync-exclude.toml` and is consumed by
`manage.py check` to silence Category 1 entries from the actionable drift
list. **Category 1 changes must land in both that toml file and this doc in
the same PR**, so the human-readable rationale stays in lockstep with the
machine-readable rules. (The mechanism uses a separate file from
`settings.toml` because `SettingsManager.save()` rewrites that one on every
sync and would clobber user-managed entries.)

> **Scope note:** by omission, every file not mentioned in one of the three
> categories below is adopted verbatim from upstream. There is no explicit
> "adopt" list — keeping the doc small is the point.

## 1. Template-skeleton files (never adopt)

These files exist upstream as part of the generic skeleton a new project would
start from. InfraFoundry is a real project with its own package structure,
tests, and documentation; upstream changes to these files should always be
skipped.

The entries below are encoded as glob patterns in
`.config/pyproject_template/sync-exclude.toml` so `manage.py check` reports
them on a separate "Skipped per project policy" summary line and does not
include them in actionable drift.

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
- `tests/template/test_properties.py` — property tests for the skeleton
  package's `greet`.
- `tests/template/test_check_template_updates.py` — template-owned (ADR-9017)
  and never adopted; excluded so the documented-path test accepts ADR-9026
  naming it (#1169).

> **Note on `tests/template/`:** this directory is **not** blanket-skipped.
> Upstream uses it for tests that exercise the `tools/pyproject_template/*`
> and `tools/doit/*` modules — modules we keep and use. Tests in this
> directory are evaluated per-file: skeleton-package tests (listed above)
> stay out of the tree; tests that cover modules we ship are adopted.
> Upstream additions to this directory surface as actionable drift in
> `manage.py check` and require an explicit per-file adopt-or-exclude
> decision.

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
  `docs/development/tooling-roles.md` — skeleton/meta docs about the
  template's own tooling choices.
  (`docs/development/dependabot-automerge.md` and `docs/development/github-repository-settings.md`
  were excluded here until #1054: adopted tests and docs now read or link them.)
- `docs/TABLE_OF_CONTENTS.md` — skeleton table of contents. Superseded by the
  mkdocs-generated nav.

### Opt-in AI hooks
- `tools/hooks/ai/cbm-*`, `tools/hooks/ai/context-mode-*` and their
  `tests/test_hook_cbm_*.py` / `tests/test_hook_context_mode_*.py` tests —
  opt-in token-efficiency hooks InfraFoundry does not use (#1169).

### Other
- `LICENSE` — InfraFoundry ships its own license; never overwrite.
- `README.template.md` — the README template for newly generated projects
  (#1169).

## 2. Infrafoundry-specific files (upstream changes never apply)

These files exist only in InfraFoundry. They are listed here so reviewers know
not to ask "should we sync this?" — there is nothing to sync from.

- `src/infrafoundry/` — the actual framework code.
- `blueprints/` — infrastructure blueprints.
- `.github/actions/install-age-sops/` — composite action that installs pinned,
  checksum-verified age and sops for `ci.yml`, `mutation.yml` and
  `daily-check.yml` (#1105).
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
- InfraFoundry-authored ADRs under `docs/decisions/` (files numbered
  `0001–0012`). Upstream ships its own ADRs in the `9000-` series under the
  same directory; those are adopted verbatim. See ADR-9016 for the two-series
  convention.

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
| `.claude/settings.json` | Preserves project-specific permissions, hooks, and environment variables. Matches upstream since #1169, which dropped the committed `bash-ban-raw-tools` wiring along with the hook (endavis/pyproject-template#1038). |
| `.github/CONTRIBUTING.md` | Preserves InfraFoundry branching/commit conventions and the issue-driven workflow description. |
| `.gitignore` | Preserves entries for `generated/`, state DB paths, `endavis-infra/`, and other InfraFoundry-specific artifacts. |
| `.envrc` | Preserves `INFRAFOUNDRY_*` environment variables and direnv layout specific to the framework. Like upstream since #1208, it no longer sets `UV_CACHE_DIR`: uv uses its shared default cache. |
| `.pre-commit-config.yaml` | Preserves InfraFoundry-specific hooks (blueprint linter, commit-msg format) alongside upstream quality hooks, and the `check-yaml` `exclude` that skips Jinja2 blueprint resource templates (every `blueprints/**/*.yaml` except `blueprint.yaml`) (#1096). |
| `CHANGELOG.md` | InfraFoundry owns this — never replaced, only appended. |
| `README.md` | Preserves InfraFoundry description, quickstart, and feature list. |
| `dodo.py` | Preserves InfraFoundry-specific task imports. |
| `mkdocs.yml` | Preserves the InfraFoundry nav tree (Providers, Runners, Configuration, etc.). |
| `pyproject.toml` | Preserves project name, dependencies, CLI entry points, and mypy/ruff overrides specific to InfraFoundry: `disallow_any_generics = true` globally with an override that turns it off for template-owned tooling (as upstream has it), the `agent_roster` import override, the InfraFoundry vulture `ignore_names` entries, and the `[tool.mutmut]` `also_copy` (`blueprints/`, `example-config/`) and `do_not_mutate` (`src/infrafoundry/core/protocols.py`) keys, checked by `tests/test_mutmut_project_paths.py` (#1108). |
| `tests/conftest.py` | Preserves InfraFoundry-specific fixtures (`mock_config_manager`, `mock_config_dir`, sample resource fixtures, etc.) alongside upstream's `mock_subprocess` fixture. |
| `tests/template/test_doit_quality.py` | Preserves the local-only `lint_blueprints` entry in the `task_check` dependency set and `TestTaskLintBlueprints`. The mypy scope assertions match upstream since #1056. |
| `tests/test_documented_paths.py` | Preserves the `HISTORICAL` exemptions for dated records (`_is_historical`), the package/provider/example-config shorthand bases (`_resolves`), the InfraFoundry `ALLOWED` entries for config-repo walkthrough paths (#1057), and an `ALLOWED` entry for the template-owned `tests/template/test_utils.py` that ADR-9017 names (#1208). The sync-exclude skip and committed-files-only scan come from upstream's `tests/doc_scan.py` since #1169 (ADR-9026). |
| `tests/test_markdown_links.py`, `tests/test_instruction_pointers.py`, `tests/test_doc_scan.py` (and `tests/test_documented_paths.py`) | Import `from tests.doc_scan import ...` instead of upstream's bare `from doc_scan import ...`: `tests/` is a package here, so mypy cannot resolve the bare name, and an `ignore_missing_imports` override would leave the `doc_scan` calls untyped (#1169). |
| `tests/test_hook_dangerous_command_matrix.py` | Preserves `dict[str, Any]` in the case-table annotations, which local `disallow_any_generics` requires. |
| `docs/development/doit-tasks-reference.md` | Upstream's text since #1208, with InfraFoundry's frontmatter, `lint_blueprints` in the `check` description, `src/infrafoundry/_version.py` for the placeholder, a local `[tool.vulture]` note in place of the link to upstream's coding-standards dead-code section (absent here), and an "InfraFoundry Tasks" section and category row for the tasks only this project has (`plan`, `apply`, `destroy`, `lint_blueprints`, `test_integration`, the `install_*` system-tool installers). |
| `docs/development/ci-cd-testing.md` | Upstream's text, localized: Linux-only platforms (ADR-0001), coverage of `infrafoundry`, the Terraform/OpenTofu/age/sops installs and Codecov upload, `doit lint_blueprints` in the `lint` row (checked by `tests/test_ci_jobs_doc.py`), the strict docs build, the `check-commit-issue-ref` hook row, no hook-skipping tip, and upstream issue numbers written as `endavis/pyproject-template#NNN` (#1057). |
| `tests/test_docs_frontmatter.py` | Preserves the `dict[str, Any]` return type on `_frontmatter`, which local `disallow_any_generics` requires (#1057). |
| `tools/doit/quality.py` | Preserves `task_lint_blueprints()` and any sibling blueprint-specific tasks. |
| `tools/doit/install_tools.py` | Preserves age/sops/terraform/opentofu installer tasks. |
| `tools/doit/testing.py` | Preserves `--cov=infrafoundry` coverage target. |
| `.github/workflows/ci.yml` | Preserves the Linux-only `runs-on: ubuntu-latest` (ADR-0001), the Terraform/OpenTofu install steps, the age/sops install through `.github/actions/install-age-sops` (#1105), the `INFRAFOUNDRY_SKIP_SOPS_CHECK` and `HYPOTHESIS_PROFILE` env vars, the `--cov=infrafoundry` flag, the Codecov upload step, and the sparse-checkout of `python-versions.json`. Verbatim adoption from upstream loses all of these — pulled forward from a sync miss in PR #836. |
| `.github/workflows/daily-check.yml` | Preserves the Terraform/OpenTofu install steps and the age/sops install through `.github/actions/install-age-sops` before `doit check`, matching `ci.yml`. Upstream installs only Python and uv, so without them the scheduled check fails on the tests that run `terraform` and `age-keygen` (#1095). |
| `.github/workflows/mutation.yml` | Preserves the age/sops install through `.github/actions/install-age-sops`, which pins both versions and checks each download's SHA-256 (#1105). Gives the `Run mutmut` step 180 minutes instead of 120, since a full run outgrew the old limit (#1116). |

When reviewing a sync PR that touches any of the above, scroll through the diff
with the spot-check note in mind. If the customization is missing from the
proposed change, the merge lost it — push back and ask for a rework.

## 4. Temporarily deferred files

Unlike the categories above, these files **will** be adopted — just not in the
current sync phase. Sync-tracker #673 completed in Phase E (issue #678); no
files are currently deferred. Future deferrals should be logged here with a
pointer to the follow-up issue.
