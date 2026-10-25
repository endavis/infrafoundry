"""A path named in the docs should exist, or be a declared placeholder.

`test_markdown_links.py` resolves link *targets* and `test_instruction_pointers.py`
resolves quoted section references and command names. Neither looks at a path
written in backticks in prose, which is how four stale references survived
long enough to be found by a manual sweep (#773):

- `.claude/claude.md` -- named four times, wrong case, and one of them an
  instruction to *verify* a file that does not exist under that name;
- `docs/installation.md`, `docs/usage.md`, `docs/api.md` in the migration guide,
  all three moved when the documentation was reorganised;
- `.github/workflows/tests.yml`, a workflow the reader was told to create;
- `.github/copilot/settings.json`, a settings file neither this repo nor the
  Copilot CLI has.

The allowlist below is the interesting half. A doc legitimately names paths that
do not exist -- placeholders substituted during setup, files created at runtime,
worked examples. Each entry states which, so the list stays a set of decisions
rather than a pile of suppressions.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

from tests.sync_excluded import is_sync_excluded

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    "site",
    "node_modules",
    "__pycache__",
    "tmp",
    ".mypy_cache",
    "worktrees",
}

# A backticked path with a directory component and a known extension. Bare
# filenames ("run `configure.py`") are shorthand, not location claims, and are
# deliberately not checked.
DOCUMENTED_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml|json|cfg|txt|sh))`")

# Allowlist entries that exist on a developer's machine but are never committed.
# They are exempt from the obsolescence check below: finding one on disk says
# nothing about whether a fresh checkout has it, and the whole point of listing
# them is that it does not.
NEVER_COMMITTED = frozenset({".claude/settings.local.json", "tmp/"})

# Paths that are allowed not to exist, and why.
ALLOWED: dict[str, str] = {
    # Substituted by configure.py when a project is created.
    "src/__PACKAGE_NAME__/": "package-name placeholder, substituted during setup",
    # Created at runtime, deliberately not checked in.
    ".config/pyproject_template/": "written by the management suite on first run",
    # Illustrative names in worked examples and templates.
    "path/to/": "generic example path",
    "src/generated/": "worked example in the rule-file READMEs (a downstream project)",
    "codegen/SKILL.md": "worked example in the rule-file READMEs",
    ".github/instructions/NAME.instructions.md": "a naming pattern, not a file",
    "tests/test_file.py": "generic example path",
    "tests/test_cache.py": "worked example in the AI walkthrough",
    "tests/test_farewell.py": "worked example in the add-a-feature tutorial",
    "tests/test_cli_farewell.py": "worked example in the add-a-feature tutorial",
    # Shorthand for a path under the user's home.
    "gh/hosts.yml": "shorthand for ~/.config/gh/hosts.yml",
    # Never committed, by policy. `.claude/settings.local.json` is blocked by the
    # `no-local-config` pre-commit hook; `tmp/` is generated output. Both exist on
    # a developer's machine and in no fresh checkout -- which is precisely why the
    # resolution below must not be satisfied by whatever happens to be on disk.
    ".claude/settings.local.json": "local config; the no-local-config hook blocks committing it",
    "tmp/": "generated artifacts and agent scratch space, gitignored",
    # AGENTS.md's before/after illustration of the temp-file convention.
    "/tmp/pr-body.md": "the 'wrong' half of the temp-file example",
    # Declared as future work.
    ".agents/skills.json": "Antigravity-side suppression, documented as planned",
    # Removed by #976; named in the ADR and consumer notes as what no longer exists.
    ".claude/commands/ghi-finalize.md": "historical reference to a file removed by #976",
    # InfraFoundry divergence (#1057): paths in a user's configuration repository,
    # named in walkthroughs that tell the reader to create or edit them.
    "envs/dev/resources/vms.yaml": "the tailscale-exit-node walkthrough's VM file",
    "envs/prod/resources/vms.yaml": "the tailscale-exit-node walkthrough's VM file",
    "envs/staging/settings.yaml": "created in the separate-config-repo walkthrough",
    ".github/workflows/deploy-infrastructure.yml": "created in the user's config repository",
    ".github/workflows/deploy.yml": "created in the user's infrastructure repository",
    "roles/webserver/": "role layout illustrated in example-config/roles/README.md",
    "roles/docker/": "role layout illustrated in example-config/roles/README.md",
    "roles/webapp/": "role layout illustrated in example-config/roles/README.md",
    "pyinfra/web.py": "a user's deploy module in the PyInfra runner example",
    "scripts/setup.sh": "package-relative event script in the infrastructure-packages example",
    "scripts/cluster-setup.sh": "package-relative event script in the ontap-cluster example",
    "proxmox/ontap-cluster/scripts/": "rewritten event script path in the ontap-cluster example",
    "envs/dev/proxmox/ontap-cluster/scripts/": "resolved event script path in the example",
    "endavis-infra/": "a separate configuration repository named in ADR-0016",
    "tests/test_release_steps_doc.py": "upstream test listed as deferred in the divergences doc",
    "tests/unit/providers/opnsense/test_dhcp_validator.py": "named in ADR-0014 as deleted",
    "tests/integration/test_opnsense_nested_plan.py": "planned in ADR-0016's test plan",
    "src/infrafoundry/providers/opnsense/validators/firewall_validator.py": (
        "ADR-0015's file list; the validator is now firewall_rule_validator.py"
    ),
}


# InfraFoundry divergence (#1057): dated records and design proposals. They name
# paths as they stood when written (or as proposed), and rewriting them would
# falsify the record.
HISTORICAL: dict[str, str] = {
    "CHANGELOG.md": "release notes describe the tree at each release",
    "docs/validation/": "dated validation reports (2025-12-23)",
    "docs/testing/TESTING_MAINTENANCE_REPORT.md": "dated test maintenance report",
    "docs/plugin_system/": "plugin-system design proposals for packages not yet built",
    "docs/architecture/plans/": "refactor plans written against the pre-refactor layout",
    "docs/development/opnsense-spike-": "spike findings; the spike code was removed",
}

# InfraFoundry divergence (#1057): besides the repo root and the doc's own
# directory, a path may be written relative to the package (`core/events/`), to a
# provider package (`services/kea_dhcp.py` in OPNsense docs), or to the example
# config repository (`envs/oci-k3s/settings.yaml`).
_SHORTHAND_BASES = (
    REPO_ROOT / "src" / "infrafoundry",
    *sorted((REPO_ROOT / "src" / "infrafoundry" / "providers").glob("*/")),
    REPO_ROOT / "example-config",
)


@cache
def _tracked_markdown() -> frozenset[str]:
    """Repo-relative paths of the committed markdown files.

    InfraFoundry divergence (#1057): git-ignored trees such as `generated/` and a
    checked-out config repo carry third-party markdown that no one here maintains.
    """
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return frozenset(out.stdout.split())


def _is_local_doc(doc: Path) -> bool:
    """Whether *doc* is a committed, non-historical document of this repository."""
    rel = doc.relative_to(REPO_ROOT).as_posix()
    return rel in _tracked_markdown() and not rel.startswith(tuple(HISTORICAL))


def _resolves(doc: Path, raw: str) -> bool:
    """Whether *raw* names an existing path from any base it may be written against."""
    bases = (REPO_ROOT, doc.parent, *_SHORTHAND_BASES)
    return any((base / raw).exists() for base in bases)


def _markdown_files(root: Path = REPO_ROOT) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.md"))
        if not any(part in SKIP_DIRS for part in path.relative_to(root).parts)
    ]


def _is_allowed(raw: str) -> bool:
    return any(raw.startswith(prefix) or raw == prefix for prefix in ALLOWED)


def _documented_paths() -> list[tuple[Path, str]]:
    """Return (doc, path) for every backticked path that claims a location."""
    found: list[tuple[Path, str]] = []
    for doc in _markdown_files():
        for match in DOCUMENTED_PATH.finditer(doc.read_text(encoding="utf-8", errors="replace")):
            raw = match.group(1)
            if "/" not in raw:
                continue  # bare filename: shorthand
            if raw.startswith(("http", "~", "{")) or "<" in raw or "*" in raw:
                continue
            found.append((doc, raw))
    return found


def test_documented_paths_exist() -> None:
    """A path in backticks should resolve, or be a declared placeholder."""
    missing = sorted(
        {
            f"{doc.relative_to(REPO_ROOT)}: {raw}"
            for doc, raw in _documented_paths()
            if _is_local_doc(doc)
            and not _is_allowed(raw)
            # InfraFoundry divergence (#1057): upstream files we deliberately exclude.
            and not is_sync_excluded(raw)
            and not _resolves(doc, raw)
        }
    )
    assert not missing, (
        "documentation names paths that do not exist:\n  "
        + "\n  ".join(missing)
        + "\nFix the path, or add it to ALLOWED with the reason it is not a real file."
    )


def test_the_scanner_skips_worktrees(tmp_path: Path) -> None:
    """Each worktree under `worktrees/` is a full copy of the repository (#854).

    Its docs name paths relative to itself, and a check run from the main
    checkout must not also judge every copy.
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kept.md").write_text("# Kept\n", encoding="utf-8")
    copy = tmp_path / "worktrees" / "feat" / "42-add-export" / "docs"
    copy.mkdir(parents=True)
    (copy / "index.md").write_text("# Copy\n", encoding="utf-8")

    assert _markdown_files(tmp_path) == [tmp_path / "docs" / "kept.md"]


def test_the_scanner_reads_something() -> None:
    """Guard against the assertion above passing on an empty scan.

    Deliberately not a threshold on the count: a downstream project has fewer
    docs than the template, and a test that fails because a project is smaller
    is the portability trap this repo warns adopters about. What matters is that
    the regex finds paths *and* that resolution works, so a scan of real files
    could report a real miss.
    """
    found = _documented_paths()
    assert found, "no documented paths found at all; the regex is not matching"
    resolved = [
        raw for doc, raw in found if (REPO_ROOT / raw).exists() or (doc.parent / raw).exists()
    ]
    assert resolved, "no documented path resolved; resolution is broken, not the docs"


def test_allowlist_entries_are_still_needed() -> None:
    """An allowlist entry for a path that now exists is a suppression to drop."""
    stale = sorted(
        prefix
        for prefix in ALLOWED
        if not prefix.endswith("/")
        and prefix not in NEVER_COMMITTED
        and (REPO_ROOT / prefix.lstrip("/")).exists()
    )
    assert not stale, (
        f"these paths exist now, so their allowlist entries are obsolete: {stale}. "
        "Remove them, so the list keeps meaning 'deliberately not a file'."
    )


def test_every_allowlist_entry_carries_a_reason() -> None:
    """The list is decisions, not suppressions."""
    for prefix, reason in ALLOWED.items():
        assert reason.strip(), f"{prefix} is allowlisted without a reason"


def test_never_committed_entries_are_allowlisted() -> None:
    """Every never-committed exemption must also carry a reason in ALLOWED.

    `NEVER_COMMITTED` only suppresses the obsolescence check. If an entry drifts
    out of `ALLOWED` it would stop being exempt from the existence check while
    still looking handled, so the two lists are held together.
    """
    for prefix in NEVER_COMMITTED:
        assert prefix in ALLOWED, f"{prefix} is exempt from staleness but not allowlisted"
