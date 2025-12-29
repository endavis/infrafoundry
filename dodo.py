import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

from rich.console import Console
from doit.tools import title_with_actions
from rich.text import Text

console = Console()

# Use direnv-managed UV_CACHE_DIR if available, otherwise use tmp/
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", "tmp/.uv_cache")

# Doit configuration
DOIT_CONFIG = {
    "verbosity": 2,
    "default_tasks": ["list"],
}


def success_message():
    console.print(
        "\n[bold green]--------------------------[/bold green]"
        " All tasks succeeded! "
        "[bold green]--------------------------[/bold green]\n"
    )


# --- Setup / Install Tasks ---


def task_install():
    """Install dependencies with uv."""
    return {
        "actions": ["uv pip install -e ."],
        "title": title_with_actions,
    }


def task_dev():
    """Install with dev dependencies."""
    return {
        "actions": ['uv pip install -e ".[dev]"'],
        "title": title_with_actions,
    }


def task_cleanup():
    """Remove build artifacts and caches."""

    def clean_artifacts():
        dirs_to_remove = [
            "build",
            "dist",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "tmp/htmlcov",
            "tmp/.coverage",
            "tmp/.pytest_cache",
            "tmp/.mypy_cache",
            "tmp/.ruff_cache",
        ]
        for d in dirs_to_remove:
            if os.path.exists(d):
                print(f"Removing {d}...")
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)

        # Recursive removal
        for root, dirs, files in os.walk("."):
            for d in dirs:
                if d == "__pycache__":
                    shutil.rmtree(os.path.join(root, d))
            for f in files:
                if f.endswith(".pyc"):
                    os.remove(os.path.join(root, f))

    return {
        "actions": [clean_artifacts],
        "title": title_with_actions,
    }


# --- Development Tasks ---


def task_test():
    """Run pytest."""
    return {
        "actions": ["pytest -v"],
        "title": title_with_actions,
    }


def task_coverage():
    """Run tests with full coverage report."""
    cmd = (
        "pytest --cov=src/infrafoundry --cov-report=term-missing "
        "--cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v"
    )
    return {
        "actions": [
            cmd,
            lambda: print(
                "\nCoverage report generated:\n  HTML: tmp/htmlcov/index.html\n"
                "  XML:  tmp/coverage.xml\n\n"
                "Target: 90% coverage"
            ),
        ],
        "title": title_with_actions,
    }


def task_test_unit():
    """Run unit tests only."""
    return {
        "actions": ["pytest -v -m unit tests/unit/"],
        "title": title_with_actions,
    }


def task_test_integration():
    """Run integration tests only."""
    return {
        "actions": ["pytest -v -m integration tests/integration/"],
        "title": title_with_actions,
    }


def task_test_fast():
    """Run fast tests (skip slow ones)."""
    return {
        "actions": ['pytest -v -m "not slow"'],
        "title": title_with_actions,
    }


def task_lint():
    """Run ruff linter."""
    return {
        "actions": ["ruff check src/ tests/"],
        "title": title_with_actions,
    }


def task_type_check():
    """Run mypy for type checking."""
    return {
        "actions": ["mypy src/"],
        "title": title_with_actions,
    }


def task_format():
    """Format code with ruff."""
    return {
        "actions": ["ruff format src/ tests/", "ruff check --fix src/ tests/"],
        "title": title_with_actions,
    }


def task_format_check():
    """Check code formatting with ruff."""
    return {
        "actions": ["ruff format --check src/ tests/"],
        "title": title_with_actions,
    }


def task_check():
    """Run all checks (lint + type check + format + coverage)."""
    return {
        "actions": [success_message],
        "task_dep": ["format_check", "lint", "type_check", "coverage"],
        "title": title_with_actions,
    }


# --- Infrastructure Tasks ---


def task_plan():
    """Generate and plan infrastructure (dry-run)."""
    return {
        "actions": ["infra plan --env %(env)s --dry-run"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }


def task_apply():
    """Apply infrastructure changes."""
    return {
        "actions": ["infra apply --env %(env)s"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }


def task_destroy():
    """Destroy infrastructure."""
    return {
        "actions": ["infra destroy --env %(env)s"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }


# --- Installation Helpers (Converted from Bash) ---


def _run_cmd_internal(cmd, shell=True, check=True):
    """Internal helper to run shell commands within python actions."""
    print(f"Executing: {cmd}")  # Print the command here.
    subprocess.run(cmd, shell=shell, check=check)


def _install_direnv():
    if shutil.which("direnv"):
        print(f"✓ direnv already installed: {subprocess.getoutput('direnv --version')}")
        return

    print("Installing direnv...")
    version = _get_latest_github_release("direnv/direnv")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        bin_url = (
            f"https://github.com/direnv/direnv/releases/download/v{version}/direnv.linux-amd64"
        )
        bin_path = os.path.join(install_dir, "direnv")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)
        _run_cmd_internal(f"chmod +x {bin_path}")
    elif system == "darwin":
        _run_cmd_internal("brew install direnv")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    # Hook setup hint
    print("✓ direnv installed. Ensure you have hooked it into your shell (e.g., ~/.bashrc).")


def task_install_direnv():
    """Install direnv."""
    return {
        "actions": [_install_direnv],
        "title": title_with_actions,
    }


def _install_age():
    if shutil.which("age"):
        print(f"✓ age already installed: {subprocess.getoutput('age --version').splitlines()[0]}")
        return

    print("Installing age...")
    version = _get_latest_github_release("FiloSottile/age")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        tar_url = f"https://github.com/FiloSottile/age/releases/download/v{version}/age-v{version}-linux-amd64.tar.gz"
        tar_path = "/tmp/age.tar.gz"
        print(f"Downloading {tar_url}...")
        urllib.request.urlretrieve(tar_url, tar_path)

        print(f"Extracting to {install_dir}...")
        with tarfile.open(tar_path, "r:gz") as tar:
            # Filter for binary files
            for member in tar.getmembers():
                if member.name.endswith("/age") or member.name.endswith("/age-keygen"):
                    # flatten structure
                    member.name = os.path.basename(member.name)
                    tar.extract(member, path=install_dir)

        os.remove(tar_path)
        _run_cmd_internal(f"chmod +x {install_dir}/age {install_dir}/age-keygen")

    elif system == "darwin":
        _run_cmd_internal("brew install age")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)
    print("✓ age installed")


def task_install_age():
    """Install age encryption tool."""
    return {
        "actions": [_install_age],
        "title": title_with_actions,
    }


def _get_latest_github_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url)

    # Use GitHub token if available to avoid rate limits
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        request.add_header("Authorization", f"token {github_token}")

    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode())
        return data["tag_name"].lstrip("v")


def _install_sops():
    if shutil.which("sops"):
        print(f"✓ SOPS already installed: {subprocess.getoutput('sops --version').splitlines()[0]}")
        return

    print("Installing SOPS...")
    version = _get_latest_github_release("getsops/sops")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        # Download binary directly
        bin_url = f"https://github.com/getsops/sops/releases/download/v{version}/sops-v{version}.linux.amd64"
        bin_path = os.path.join(install_dir, "sops")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)
        _run_cmd_internal(f"chmod +x {bin_path}")
    elif system == "darwin":
        _run_cmd_internal("brew install sops")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)
    print(f"✓ SOPS {version} installed")


def task_install_sops():
    """Install SOPS secrets manager."""
    return {
        "actions": [_install_sops],
        "title": title_with_actions,
    }


def _install_terraform():
    # Get latest version
    url = "https://api.github.com/repos/hashicorp/terraform/releases/latest"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            latest_version = data["tag_name"].lstrip("v")
    except Exception as e:
        print(f"Failed to fetch latest terraform version: {e}")
        return

    if shutil.which("terraform"):
        current_json = subprocess.getoutput("terraform version -json")
        try:
            current_version = json.loads(current_json)["terraform_version"]
            if current_version == latest_version:
                print(f"✓ Terraform already up to date: {latest_version}")
                return
            print(f"Current version: {current_version}, upgrading to: {latest_version}")
        except Exception:
            print("Could not parse current terraform version, reinstalling...")

    print(f"Installing Terraform {latest_version}...")
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map machine to terraform arch
    if machine == "x86_64":
        arch = "amd64"
    elif machine == "aarch64" or machine == "arm64":
        arch = "arm64"
    else:
        arch = "amd64"  # Fallback

    if system == "linux":
        os_name = "linux"
    elif system == "darwin":
        os_name = "darwin"
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    download_url = f"https://releases.hashicorp.com/terraform/{latest_version}/terraform_{latest_version}_{os_name}_{arch}.zip"
    zip_path = "/tmp/terraform.zip"

    print(f"Downloading {download_url}...")
    urllib.request.urlretrieve(download_url, zip_path)

    install_dir = os.path.expanduser("~/.local/bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)

    print(f"Unzipping to {install_dir}...")
    _run_cmd_internal(f"unzip -o {zip_path} -d {install_dir}")
    _run_cmd_internal(f"chmod +x {install_dir}/terraform")
    os.remove(zip_path)
    print(f"✓ Terraform {latest_version} installed to {install_dir}")


def task_install_terraform():
    """Install Terraform."""
    return {
        "actions": [_install_terraform],
        "title": title_with_actions,
    }


def task_install_ansible():
    """Install Ansible via uv."""

    def install_ansible():
        # uv is assumed to be installed
        # Check if we're in a virtual environment or need --system
        in_venv = (
            os.environ.get("VIRTUAL_ENV")
            or hasattr(sys, "real_prefix")
            or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        )
        system_flag = "" if in_venv else "--system"

        if os.path.exists("pyproject.toml"):
            print("Installing InfraFoundry with Ansible...")
            _run_cmd_internal(f"uv pip install {system_flag} -e .")
        else:
            print("Installing Ansible directly...")
            _run_cmd_internal(f"uv pip install {system_flag} ansible")

    return {
        "actions": [install_ansible],
        "title": title_with_actions,
    }


def task_install_deps():
    """Install all system dependencies."""
    return {
        "actions": [lambda: print("✓ All dependencies installed successfully!")],
        "task_dep": [
            "install_direnv",
            "install_age",
            "install_sops",
            "install_terraform",
            "install_ansible",
        ],
        "title": title_with_actions,
    }


def task_setup_vscode():
    """Display VS Code extension installation tips."""
    msg = """
VS Code Extensions Setup
========================

When you open this workspace in VS Code, you'll be prompted to install
recommended extensions. Alternatively, you can:

1. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)
2. Type 'Extensions: Show Recommended Extensions'
3. Click 'Install All' button

Recommended extensions include:
  • Python development tools (Pylance, debugpy)
  • Code quality (Ruff, Black)
  • Testing (pytest)
  • Infrastructure (Terraform, Ansible)
  • Git tools (GitLens)

See .vscode/extensions.json for the complete list.
"""
    return {
        "actions": [lambda: print(msg)],
        "title": title_with_actions,
    }


# ==============================================================================
# Governance Validation Helpers
# ==============================================================================


def validate_merge_commits(console: "Console") -> bool:
    """Validate that all merge commits follow the required format.

    Returns:
        bool: True if all merge commits are valid, False otherwise.
    """
    import re

    console.print("\n[cyan]Validating merge commit format...[/cyan]")

    # Get merge commits since last tag (or all if no tags)
    try:
        last_tag = subprocess.getoutput("git describe --tags --abbrev=0 2>/dev/null").strip()
        if last_tag:
            range_spec = f"{last_tag}..HEAD"
        else:
            range_spec = "HEAD"

        merge_commits = subprocess.getoutput(
            f'git log --merges --pretty=format:"%h %s" {range_spec}'
        ).strip().split('\n')

    except Exception as e:
        console.print(f"[yellow]⚠ Could not check merge commits: {e}[/yellow]")
        return True  # Don't block on this check

    if not merge_commits or merge_commits == ['']:
        console.print("[green]✓ No merge commits to validate.[/green]")
        return True

    # Pattern: <type>: <subject> (merges PR #XX, closes #YY) or (merges PR #XX)
    merge_pattern = re.compile(
        r'^[a-f0-9]+\s+(feat|fix|refactor|docs|test|chore|ci|perf):\s.+\s\(merges PR #\d+(?:, closes #\d+)?\)$'
    )

    invalid_commits = []
    for commit in merge_commits:
        if commit and not merge_pattern.match(commit):
            invalid_commits.append(commit)

    if invalid_commits:
        console.print("[bold red]❌ Invalid merge commit format found:[/bold red]")
        for commit in invalid_commits:
            console.print(f"  [red]{commit}[/red]")
        console.print("\n[yellow]Expected format:[/yellow]")
        console.print("  <type>: <subject> (merges PR #XX, closes #YY)")
        console.print("  <type>: <subject> (merges PR #XX)")
        return False

    console.print("[green]✓ All merge commits follow required format.[/green]")
    return True


def validate_issue_links(console: "Console") -> bool:
    """Validate that commits (except docs) reference issues.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    import re

    console.print("\n[cyan]Validating issue links in commits...[/cyan]")

    try:
        # Get commits since last tag
        last_tag = subprocess.getoutput("git describe --tags --abbrev=0 2>/dev/null").strip()
        if last_tag:
            range_spec = f"{last_tag}..HEAD"
        else:
            # If no tags, check last 10 commits
            range_spec = "HEAD~10..HEAD"

        commits = subprocess.getoutput(
            f'git log --pretty=format:"%h %s" {range_spec}'
        ).strip().split('\n')

    except Exception as e:
        console.print(f"[yellow]⚠ Could not check issue links: {e}[/yellow]")
        return True  # Don't block on this check

    if not commits or commits == ['']:
        console.print("[green]✓ No commits to validate.[/green]")
        return True

    issue_pattern = re.compile(r'#\d+')
    docs_pattern = re.compile(r'^[a-f0-9]+\s+docs:', re.IGNORECASE)

    commits_without_issues = []
    for commit in commits:
        if commit:
            # Skip docs commits
            if docs_pattern.match(commit):
                continue
            # Skip merge commits (already validated separately)
            if 'merge' in commit.lower():
                continue
            # Check for issue reference
            if not issue_pattern.search(commit):
                commits_without_issues.append(commit)

    if commits_without_issues:
        console.print("[bold yellow]⚠ Warning: Some commits don't reference issues:[/bold yellow]")
        for commit in commits_without_issues[:5]:  # Show first 5
            console.print(f"  [yellow]{commit}[/yellow]")
        if len(commits_without_issues) > 5:
            console.print(f"  [dim]...and {len(commits_without_issues) - 5} more[/dim]")
        console.print("\n[dim]This is a warning only - release can continue.[/dim]")
        console.print("[dim]Consider linking commits to issues for better traceability.[/dim]")
    else:
        console.print("[green]✓ All non-docs commits reference issues.[/green]")

    return True  # Warning only, don't block release


# ==============================================================================
# Release Tasks
# ==============================================================================


def task_release_dev(type="alpha"):
    """Create a pre-release (alpha/beta/rc) tag for TestPyPI and push to GitHub.

    Args:
        type (str): Pre-release type (e.g., 'alpha', 'beta', 'rc'). Defaults to 'alpha'.
    """

    def create_dev_release():
        console = Console()
        console.print("=" * 70)
        console.print(f"[bold green]Starting {type} release tagging...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.getoutput("git branch --show-current").strip()
        if current_branch != "main":
            console.print(f"[bold yellow]⚠ Warning: Not on main branch (currently on {current_branch})[/bold yellow]")
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.getoutput("git status -s").strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run("git pull", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run("doit check", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Pre-release checks failed! Please fix issues before tagging.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and tagging
        console.print(f"\n[cyan]Bumping version ({type}) and updating changelog...[/cyan]")
        try:
            # Use cz bump --prerelease <type> --changelog
            result = subprocess.run(
                f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz bump --prerelease {type} --changelog",
                shell=True, check=True, capture_output=True, text=True
            )
            console.print(f"[green]✓ Version bumped to {type}.[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version
            version_match = Text(result.stdout).search(r"Bumping to version (\d+\.\d+\.\d+[^\s]*)")
            if version_match:
                new_version = version_match.group(1)
            else:
                new_version = "unknown"

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ commitizen bump failed![/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print(f"\n[cyan]Pushing tag v{new_version} to origin...[/cyan]")
        try:
            subprocess.run(f"git push --follow-tags origin {current_branch}", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Tags pushed to origin.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pushing tag to origin:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Development release {new_version} complete![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions (testpypi.yml) for the TestPyPI publish.")
        console.print("2. Verify on TestPyPI once the workflow completes.")

    return {
        "actions": [create_dev_release],
        "params": [
            {
                "name": "type",
                "short": "t",
                "long": "type",
                "default": "alpha",
                "help": "Pre-release type (alpha, beta, rc)",
            }
        ],
        "title": title_with_actions,
    }


def task_release():
    """Automate release: bump version, update CHANGELOG, and push to GitHub (triggers CI/CD)."""

    def automated_release():
        console = Console()
        console.print("=" * 70)
        console.print("[bold green]Starting automated release process...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.getoutput("git branch --show-current").strip()
        if current_branch != "main":
            console.print(f"[bold yellow]⚠ Warning: Not on main branch (currently on {current_branch})[/bold yellow]")
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.getoutput("git status -s").strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run("git pull", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Governance validation
        console.print("\n[bold cyan]Running governance validations...[/bold cyan]")

        # Validate merge commit format (blocking)
        if not validate_merge_commits(console):
            console.print("\n[bold red]❌ Merge commit validation failed![/bold red]")
            console.print("[yellow]Please ensure all merge commits follow the format:[/yellow]")
            console.print("[yellow]  <type>: <subject> (merges PR #XX, closes #YY)[/yellow]")
            sys.exit(1)

        # Validate issue links (warning only)
        validate_issue_links(console)

        console.print("[bold green]✓ Governance validations complete.[/bold green]")

        # Run all checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run("doit check", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Pre-release checks failed! Please fix issues before releasing.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and CHANGELOG generation using commitizen
        console.print("\n[cyan]Bumping version and generating CHANGELOG with commitizen...[/cyan]")
        try:
            # Use cz bump --changelog --merge-prerelease to update version, changelog, commit, and tag
            # This consolidates pre-release changes into the final release entry
            result = subprocess.run(
                f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz bump --changelog --merge-prerelease",
                shell=True, check=True, capture_output=True, text=True
            )
            console.print("[green]✓ Version bumped and CHANGELOG updated (merged pre-releases).[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version from cz output (example: "Bumping to version 1.0.0")
            version_match = Text(result.stdout).search(r"Bumping to version (\d+\.\d+\.\d+)")
            if version_match:
                new_version = version_match.group(1)
            else:
                new_version = "unknown" # Fallback if regex fails

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ commitizen bump failed! Ensure your commit history is conventional.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]❌ An unexpected error occurred during commitizen bump: {e}[/bold red]")
            sys.exit(1)

        # Push commits and tags to GitHub
        console.print("\n[cyan]Pushing commits and tags to GitHub...[/cyan]")
        try:
            subprocess.run(f"git push --follow-tags origin {current_branch}", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Pushed new commits and tags to GitHub.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pushing to GitHub:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Automated release {new_version} complete![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions for build and publish.")
        console.print("2. Check PyPI: https://pypi.org/project/infrafoundry/")
        console.print("3. Verify the updated CHANGELOG.md in the repository.")

    return {
        "actions": [automated_release],
        "title": title_with_actions,
    }
