# Security Triage

Triage a finding from `doit security` (bandit) or `doit audit` (pip-audit): fixed, justified with a
named reason, or escalated to the user. Never silenced by a suppression nobody can account for.

Argument: `$ARGUMENTS` — optional: `bandit` or `pip-audit`, to triage only that scanner's findings.
Empty runs and triages both.

Before Step 1, read `.github/CONTRIBUTING.md` and locate the "### Checks" section. It documents the
`security` extra both scanners need. This command is the rest of the procedure: bandit's `# nosec`
convention and pip-audit's advisory handling were unwritten before it (#834).

## Instructions

### Step 1: Run both scanners

Run `doit security` and `doit audit` (or `doit check`, which runs both along with everything else).

Both need the `security` extra. Without it they print an install hint and exit 0, a pass that
checked nothing. If you see the hint, run `doit install_dev` — never `uv sync --extra security`
alone, which syncs to exactly that extra and uninstalls the `dev` extra's tools `doit check` itself
needs — and run the task again. Triage nothing until you have seen a real scan.

A sample under `tmp/agents/claude/` is not a stand-in for the real file: `[tool.bandit]
exclude_dirs` in `pyproject.toml` excludes `tmp`, so a bandit run scoped there reports zero
findings regardless of what the sample contains. That is a second way to get a clean result you
have not earned — triage the finding against the real flagged file, under `src/`, `tools/` or
`bootstrap.py`.

### Step 2: Triage a bandit finding

For each finding bandit reports:

1. **Fix it**, if the pattern can go: list-form `subprocess` arguments instead of a string with
   `shell=True`, `yaml.safe_load` instead of `yaml.load`, a validated path instead of an unvalidated
   one.
2. **Justify it**, if the flagged code is safe: add `# nosec <ID> - <reason>`, naming only the test
   IDs bandit reported on that line. A per-ID suppression is precise — `# nosec B602` clears only
   B602, and bandit still reports every other test ID on that line. **Never a bare `# nosec`.** It
   silences every finding on the line, not only the one you meant to justify.
3. **Stop and ask before adding a new `skips` entry.** `[tool.bandit] skips` in `pyproject.toml`
   disables a test repository-wide, for every file, not just the line in front of you.

### Step 3: Triage a pip-audit finding

For each vulnerability pip-audit reports:

1. **Locate it.** pip-audit audits the whole environment, so most findings are transitive, not a
   `pyproject.toml` entry. Check `[project] dependencies` and the `dev`/`security` extras for the
   package first. If it is not there, run `uv tree --invert --package <package>` to see what pulls
   it in.
2. **Direct dependency, fixed version exists:** hand the user the exact command for the table it is
   already in — `uv add "<package>>=<fixed version>"` for `[project] dependencies`,
   `uv add --optional dev "<package>>=<fixed version>"` for the `dev` extra, or
   `uv add --optional security "<package>>=<fixed version>"` for the `security` extra, matching
   `add-dependency`'s placement table. You cannot run this yourself; the dangerous-command hook
   blocks `uv add` for every agent, the same as it does for a brand-new dependency. The wrong flag
   lands the package in the wrong table — a `dev` or `security` package with no flag becomes a
   runtime dependency.
3. **Transitive dependency, fixed version exists:** run `uv lock --upgrade-package <package>`
   yourself — the hook does not block `uv lock`, and unlike `uv add` it changes `uv.lock` alone,
   adding no new dependency. Confirm with `git diff uv.lock` that the fixed version landed. If a
   parent's own constraint blocks the fix, stop and report it. Never add the transitive package as
   a new direct dependency just to force its version — that is a new dependency, and it goes
   through `add-dependency`.
4. If no fixed version exists at all, **assess reachability**: does this project actually call the
   vulnerable code path, or is the package present only for a feature this project does not use?
5. **Stop and ask before ignoring a pip-audit advisory.** Adding `--ignore-vuln` to `doit audit` is
   the user's decision, not yours to make by editing `tools/doit/security.py`.

### Step 4: Validate

Run `doit check`. Stop at the first failure and report it. Never edit a test to make it pass, and
never weaken a bandit or pip-audit finding just to get a clean run — an unjustified suppression is
the same shortcut this check exists to catch.

### Step 5: Record

The reason for every `# nosec`, every accepted advisory, and every pip-audit upgrade belongs in the
PR description, not only in this conversation: which finding, why it is safe or fixed, whether
Step 3 upgraded a direct or a transitive package, and what Step 2 or Step 3 ruled out. A reviewer
should not have to re-run the scanner to find out why the project still trips a bandit test or
still depends on a package with an open advisory.

When the task is done, hand off to `/ghi-finalize`, and make sure the PR body it drafts carries this
record.

## Notes

- Bandit's `# nosec` parser reads every word after the IDs as a candidate test ID and prints a
  harmless warning for each one that is not — the suppression still applies; keep reasons short
  regardless.
- Write scratch files to `tmp/agents/claude/` with the issue number in the name, and delete them
  when the task is done.
