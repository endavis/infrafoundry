"""
Helper script to apply this template onto an existing repository.

Usage:
    python tools/pyproject_template/migrate_existing_project.py --target /path/to/existing/repo
    # Optional: download the template archive (no local checkout needed)
    python tools/pyproject_template/migrate_existing_project.py --target /path/to/repo --download

What it does:
    - Optionally downloads the template (zip/tar) into target/tmp and extracts it
    - Backs up any files/dirs it would overwrite into a timestamped backup folder
      (under target/tmp/)
    - Copies core template files (tooling, docs, workflows, editor config)
    - Prints a summary of moved/backed-up items and next steps

This does NOT run the interactive configurator or move your source code. After
copying, you still need to:
    - Run `python configure.py` in the target repo to set project/package info
    - Move your code into src/<package_name>/ and fix imports
    - Merge dependencies/metadata into the new pyproject.toml
    - Regenerate uv.lock and rerun checks
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

# Support running as script or as module
_script_dir = Path(__file__).parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

# Import shared utilities
from utils import TEMPLATE_URL, Logger, download_and_extract_archive  # noqa: E402

DEFAULT_ARCHIVE_URL = f"{TEMPLATE_URL}/archive/refs/heads/main.zip"


TEMPLATE_REL_PATHS: tuple[str, ...] = (
    # Config and tooling
    "pyproject.toml",
    "dodo.py",
    "tools/pyproject_template/configure.py",
    ".envrc",
    ".envrc.local.example",
    ".pre-commit-config.yaml",
    ".python-version",
    "mkdocs.yml",
    ".editorconfig",
    ".gitignore",
    "src/package_name",
    # Docs and guides
    "AGENTS.md",
    "CHANGELOG.md",
    "docs",
    "examples",
    # Project scaffolding / automation
    ".github",
    ".devcontainer",
    ".vscode",
    ".claude",
    ".codex",
    ".gemini",
    "tools",
    "tmp/.gitkeep",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy pyproject-template scaffolding into an existing repo with backups.",
    )
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="Path to the existing repository you want to update.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Path to the pyproject-template root (defaults to this script's "
        "repo unless --download).",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download the template archive into target/tmp instead of using a local checkout.",
    )
    parser.add_argument(
        "--archive-url",
        type=str,
        default=DEFAULT_ARCHIVE_URL,
        help=f"URL to template archive (zip/tarball). Default: {DEFAULT_ARCHIVE_URL}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without making changes.",
    )
    return parser.parse_args(argv)


def ensure_exists(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_migrate(
    target: Path,
    template: Path | None = None,
    download: bool = False,
    archive_url: str = DEFAULT_ARCHIVE_URL,
    dry_run: bool = False,
) -> int:
    """Migrate an existing project to use pyproject-template.

    Args:
        target: Path to the existing repository to update.
        template: Path to the pyproject-template root.
        download: Download the template archive instead of using local checkout.
        archive_url: URL to template archive.
        dry_run: Show what would be done without making changes.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    target_root = target.resolve()

    if download:
        if dry_run:
            Logger.info(f"Dry run: Would download template from {archive_url}")
            template_root = Path(__file__).resolve().parent.parent.parent
        else:
            tmp_dir = target_root / "tmp"
            ensure_exists(tmp_dir)
            print(f"Downloading template archive from {archive_url} ...")

            template_root = download_and_extract_archive(archive_url, tmp_dir)
            Logger.success(f"Template downloaded to {template_root}")
    else:
        # Default to the root of the repo containing this script
        # Script is at tools/pyproject_template/migrate_existing_project.py
        # Root is ../../..
        template_root = (template or Path(__file__).resolve().parent.parent.parent).resolve()

    if not template_root.exists():
        Logger.error(f"Template path does not exist: {template_root}")
        return 1
    if not target_root.exists():
        Logger.error(f"Target path does not exist: {target_root}")
        return 1

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = target_root / "tmp" / f"template-migration-backup-{timestamp}"

    backed_up: list[tuple[Path, Path]] = []
    copied: list[Path] = []
    skipped: list[Path] = []
    would_backup: list[Path] = []

    for rel in TEMPLATE_REL_PATHS:
        src = template_root / rel
        dst = target_root / rel

        if not src.exists():
            skipped.append(src)
            continue

        if dst.exists():
            if dry_run:
                would_backup.append(dst)
            else:
                backup_path = backup_root / rel
                ensure_exists(backup_path.parent)
                shutil.move(str(dst), str(backup_path))
                backed_up.append((dst, backup_path))

        if dry_run:
            copied.append(dst)
        else:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                ensure_exists(dst.parent)
                shutil.copy2(src, dst)
            copied.append(dst)

    print("\n=== Template Migration Helper ===")
    print(f"Template: {template_root}")
    print(f"Target  : {target_root}")
    if dry_run:
        print("Mode    : DRY RUN (no changes made)")
    else:
        print(f"Backup  : {backup_root}")
    print()

    if copied:
        print("Would copy:" if dry_run else "Copied:")
        for path in copied:
            print(f"  - {path.relative_to(target_root)}")
    else:
        print("Copied: (none)")

    print()
    if dry_run and would_backup:
        print("Would back up existing items before overwrite:")
        for path in would_backup:
            print(f"  - {path.relative_to(target_root)}")
    elif backed_up:
        print("Backed up existing items before overwrite:")
        for original, backup in backed_up:
            print(f"  - {original.relative_to(target_root)} -> {backup.relative_to(target_root)}")
    else:
        print("Backed up: (none needed)")

    if skipped:
        print()
        print("Skipped (not present in template):")
        for path in skipped:
            print(f"  - {path.relative_to(template_root)}")

    if dry_run:
        print("\nDry run complete - no changes were made.")
    else:
        print("\nNext steps:")
        print(" 1) Run: python tools/pyproject_template/configure.py")
        print(" 2) Move your source code into src/<package_name>/ and fix imports")
        print(" 3) Merge your dependencies into pyproject.toml")
        print(" 4) Run: uv sync && doit check")
        print(" 5) Review backed-up files and port any custom content")
        print("\nFuture updates:")
        print(" • Run: python tools/pyproject_template/check_template_updates.py")
        print(" • This will show what changed in the template since migration")
        print("\nDone.")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI usage."""
    args = parse_args(argv)
    return run_migrate(
        target=args.target,
        template=args.template,
        download=args.download,
        archive_url=args.archive_url,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    import sys

    print("This script should not be run directly.")
    print("Please use: python manage.py")
    sys.exit(1)
