#!/usr/bin/env python3
"""
bootstrap.py - Single-command setup for pyproject-template

This script provides two modes of operation:

1. Default (no flags): Downloads setup tools to a temp directory and runs the
   repository setup wizard for creating new projects.

2. --sync: Downloads the template management suite permanently to
   tools/pyproject_template/ for existing projects that want to use manage.py
   for ongoing template synchronization.

Usage:
    # New project setup (default)
    curl -sSL https://raw.githubusercontent.com/endavis/pyproject-template/main/bootstrap.py \
        | python3

    # Install management suite for existing project
    curl -sSL https://raw.githubusercontent.com/endavis/pyproject-template/main/bootstrap.py \
        | python3 - --sync
"""

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# Base URL for raw files
REPO_OWNER = "endavis"
REPO_NAME = "pyproject-template"
BRANCH = "main"
BASE_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"

# Files needed for new project setup (downloaded to temp dir, runs wizard)
SETUP_FILES = [
    "tools/pyproject_template/__init__.py",
    "tools/pyproject_template/utils.py",
    "tools/pyproject_template/setup_repo.py",
    "tools/pyproject_template/configure.py",
]

# Files needed for template sync management (installed permanently)
SYNC_FILES = [
    "tools/pyproject_template/__init__.py",
    "tools/pyproject_template/utils.py",
    "tools/pyproject_template/settings.py",
    "tools/pyproject_template/check_template_updates.py",
    "tools/pyproject_template/manage.py",
    "tools/pyproject_template/configure.py",
    "tools/pyproject_template/cleanup.py",
]


def download_file(url: str, dest: Path) -> None:
    """Download a file from a URL to a local path."""
    try:
        with urllib.request.urlopen(url) as response:  # nosec B310
            content = response.read().decode("utf-8")
            dest.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        sys.exit(1)


def detect_project_settings(project_root: Path) -> dict[str, str]:
    """Detect project settings from pyproject.toml if it exists.

    Returns a dict with keys matching settings.toml [project] fields.
    """
    settings: dict[str, str] = {}
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return settings

    try:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})

        name = project.get("name", "")
        if name:
            settings["project_name"] = name
            settings["package_name"] = name.lower().replace("-", "_")
            settings["pypi_name"] = name.lower().replace("_", "-")

        description = project.get("description", "")
        if description:
            settings["description"] = description

        authors = project.get("authors", [])
        if authors:
            first = authors[0]
            if "name" in first:
                settings["author_name"] = first["name"]
            if "email" in first:
                settings["author_email"] = first["email"]

        repo_url = project.get("urls", {}).get("Repository", "")
        if repo_url:
            parsed = urlparse(repo_url)
            if parsed.netloc == "github.com" or parsed.netloc.endswith(".github.com"):
                segments = parsed.path.strip("/").split("/")
                if len(segments) >= 2:
                    settings["github_user"] = segments[0]
                    settings["github_repo"] = segments[1].removesuffix(".git")

    except Exception as e:
        print(f"  Warning: Could not parse pyproject.toml: {e}")

    return settings


def create_settings_file(project_root: Path, settings: dict[str, str]) -> Path:
    """Create .config/pyproject_template/settings.toml with detected settings.

    Returns the path to the created file.
    """
    settings_dir = project_root / ".config" / "pyproject_template"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.toml"

    lines = ["[project]"]
    for key in (
        "project_name",
        "package_name",
        "pypi_name",
        "description",
        "author_name",
        "author_email",
        "github_user",
        "github_repo",
    ):
        value = settings.get(key, "")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key} = "{escaped}"')

    lines.append("")
    lines.append("[template]")
    lines.append('commit = ""')
    lines.append('commit_date = ""')
    lines.append("")

    settings_path.write_text("\n".join(lines), encoding="utf-8")
    return settings_path


def run_sync(project_root: Path) -> None:
    """Install the template management suite for an existing project."""
    print(f"Installing {REPO_NAME} management suite...")
    print()

    pkg_dir = project_root / "tools" / "pyproject_template"

    # Check if already installed
    if pkg_dir.exists() and (pkg_dir / "manage.py").exists():
        print("  tools/pyproject_template/ already exists.")
        response = input("  Overwrite with latest versions? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            print("  Cancelled.")
            sys.exit(0)
        print()

    # Create directory structure
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Download sync files
    for file_path in SYNC_FILES:
        filename = Path(file_path).name
        url = f"{BASE_URL}/{file_path}"
        dest = pkg_dir / filename
        print(f"  Downloading {filename}...")
        download_file(url, dest)

    print()

    # Detect and create settings
    print("  Detecting project settings from pyproject.toml...")
    settings = detect_project_settings(project_root)
    settings_path = create_settings_file(project_root, settings)
    print(f"  Created {settings_path.relative_to(project_root)}")

    if settings:
        print()
        print("  Detected:")
        for key, value in settings.items():
            print(f"    {key}: {value}")

    print()

    # Verify installation
    print("  Verifying installation...")
    try:
        import subprocess  # nosec B404

        result = subprocess.run(
            [sys.executable, str(pkg_dir / "manage.py"), "--dry-run", "check"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        if result.returncode == 0:
            print("  Verification passed.")
        else:
            print(f"  Warning: Verification returned non-zero exit code ({result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr.strip()}")
    except Exception as e:
        print(f"  Warning: Could not verify installation: {e}")

    print()
    print("Installation complete!")
    print()
    print("Next steps:")
    print("  1. Review .config/pyproject_template/settings.toml")
    print("  2. Run: python tools/pyproject_template/manage.py check")
    print("  3. Apply relevant template updates")
    print("  4. Run: python tools/pyproject_template/manage.py sync")


def run_setup() -> None:
    """Run the new project setup wizard (original behavior)."""
    print(f"Bootstrapping {REPO_NAME} setup...")

    # Create temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir)

        # Recreate the package structure: tools/pyproject_template/
        pkg_dir = root_path / "tools" / "pyproject_template"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Download files
        for file_path in SETUP_FILES:
            url = f"{BASE_URL}/{file_path}"
            dest = pkg_dir / Path(file_path).name
            print(f"  Downloading {Path(file_path).name}...")
            download_file(url, dest)

        print("\nStarting setup wizard...\n")

        # Add the temp root to sys.path so 'tools.pyproject_template' can be imported
        sys.path.insert(0, str(root_path))

        # Import and run the setup module
        try:
            from tools.pyproject_template.setup_repo import main as setup_main

            setup_main()
        except ImportError as e:
            print(f"Error importing setup script: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Setup failed: {e}")
            sys.exit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description="Bootstrap pyproject-template for new or existing projects.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Install template management suite for an existing project "
        "(downloads to tools/pyproject_template/)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    if args.sync:
        project_root = Path.cwd()
        run_sync(project_root)
    else:
        run_setup()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
