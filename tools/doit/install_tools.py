"""InfraFoundry tool installation tasks.

Extends the reusable GitHub release install framework with
project-specific tools: age, sops, terraform, opentofu, ansible.
"""

import json
import os
import platform
import shutil
import subprocess  # nosec B404 - subprocess is required for version checks
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from doit.tools import title_with_actions


def get_latest_github_release(repo: str) -> str:
    """Get the latest release version for a GitHub repository.

    Queries the GitHub API for the latest release tag. Supports
    authenticated requests via GITHUB_TOKEN environment variable.

    Args:
        repo: GitHub repository in "owner/name" format (e.g. "direnv/direnv").

    Returns:
        Version string with leading 'v' stripped (e.g. "2.34.0").
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url)

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        request.add_header("Authorization", f"token {github_token}")

    with urllib.request.urlopen(request) as response:  # nosec B310 - URL is hardcoded GitHub API
        data = json.loads(response.read().decode())
        tag_name: str = data["tag_name"]
        return tag_name.lstrip("v")


def get_install_dir() -> Path:
    """Get the standard installation directory for user-local binaries.

    Returns:
        Path to ~/.local/bin, created if it does not exist.
    """
    install_dir = Path.home() / ".local" / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)
    return install_dir


def download_github_release_binary(
    repo: str, version: str, asset_pattern: str, dest_name: str
) -> Path:
    """Download a binary asset from a GitHub release.

    Args:
        repo: GitHub repository in "owner/name" format.
        version: Release version (without leading 'v').
        asset_pattern: Filename pattern with {version} placeholder.
        dest_name: Name of the installed binary.

    Returns:
        Path to the downloaded and installed binary.
    """
    asset_name = asset_pattern.format(version=version)
    url = f"https://github.com/{repo}/releases/download/v{version}/{asset_name}"
    install_dir = get_install_dir()
    dest_path = install_dir / dest_name

    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, dest_path)  # nosec B310 - downloading from constructed GitHub release URL
    dest_path.chmod(0o755)  # nosec B103 - rwxr-xr-x is required for executable binary

    return dest_path


def install_tool(
    name: str,
    repo: str,
    asset_patterns: dict[str, str],
    version_cmd: list[str] | None = None,
    post_install_message: str | None = None,
) -> None:
    """Install a tool from GitHub releases if not already present.

    Args:
        name: Tool name used for PATH lookup and as the binary dest name.
        repo: GitHub repository in "owner/name" format.
        asset_patterns: Mapping of platform.system().lower() values to asset filename patterns.
        version_cmd: Command list to run for checking installed version.
        post_install_message: Optional message printed after installation.
    """
    if version_cmd is None:
        version_cmd = [name, "--version"]

    if shutil.which(name):
        result = subprocess.run(
            version_cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        version_output = result.stdout.strip() or result.stderr.strip()
        print(f"\u2713 {name} already installed: {version_output}")
        return

    print(f"Installing {name}...")
    version = get_latest_github_release(repo)
    print(f"Latest version: {version}")

    system = platform.system().lower()
    if system == "darwin":
        subprocess.run(["brew", "install", name], check=True)
    elif system in asset_patterns:
        download_github_release_binary(
            repo=repo,
            version=version,
            asset_pattern=asset_patterns[system],
            dest_name=name,
        )
    else:
        print(f"Unsupported OS for {name}: {system}")
        sys.exit(1)

    print(f"\u2713 {name} installed.")
    if post_install_message:
        print(post_install_message)


def create_install_task(
    name: str,
    repo: str,
    asset_patterns: dict[str, str],
    version_cmd: list[str] | None = None,
    post_install_message: str | None = None,
) -> dict[str, Any]:
    """Create a doit task dict for installing a tool from GitHub releases.

    Args:
        name: Tool name used for PATH lookup and as the binary dest name.
        repo: GitHub repository in "owner/name" format.
        asset_patterns: Mapping of platform names to asset filename patterns.
        version_cmd: Command list for version check.
        post_install_message: Optional message printed after installation.

    Returns:
        A doit task dictionary with actions and title.
    """

    def _action() -> None:
        install_tool(
            name=name,
            repo=repo,
            asset_patterns=asset_patterns,
            version_cmd=version_cmd,
            post_install_message=post_install_message,
        )

    return {
        "actions": [_action],
        "title": title_with_actions,
    }


# ---------------------------------------------------------------------------
# Project-specific tool installers (tools that need custom install logic)
# ---------------------------------------------------------------------------


def _install_age() -> None:
    """Install age encryption tool (requires tar extraction)."""
    if shutil.which("age"):
        result = subprocess.run(["age", "--version"], capture_output=True, text=True, check=True)
        print(f"\u2713 age already installed: {result.stdout.strip()}")
        return

    print("Installing age...")
    version = get_latest_github_release("FiloSottile/age")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    if system == "darwin":
        subprocess.run(["brew", "install", "age"], check=True)
    elif system == "linux":
        install_dir = get_install_dir()
        tar_url = f"https://github.com/FiloSottile/age/releases/download/v{version}/age-v{version}-linux-amd64.tar.gz"
        tar_path = Path("/tmp/age.tar.gz")  # nosec B108
        print(f"Downloading {tar_url}...")
        urllib.request.urlretrieve(tar_url, tar_path)  # nosec B310

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall("/tmp")  # nosec B202
        for binary in ("age", "age-keygen"):
            src = Path("/tmp/age") / binary
            dest = install_dir / binary
            shutil.move(str(src), str(dest))
            dest.chmod(0o755)  # nosec B103
        tar_path.unlink()
        shutil.rmtree("/tmp/age", ignore_errors=True)
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    print("\u2713 age installed.")


def _install_hashicorp_zip(
    name: str, repo: str, url_template: str, binary_name: str | None = None
) -> None:
    """Install a HashiCorp-style tool distributed as a zip archive.

    Args:
        name: Display name (e.g. "Terraform").
        repo: GitHub repo for version lookup.
        url_template: Download URL with {version}, {os}, {arch} placeholders.
        binary_name: Binary name inside zip (defaults to lowercase name).
    """
    if binary_name is None:
        binary_name = name.lower()

    version = get_latest_github_release(repo)

    if shutil.which(binary_name):
        version_json = subprocess.getoutput(f"{binary_name} version -json")
        try:
            current = json.loads(version_json)["terraform_version"]
            if current == version:
                print(f"\u2713 {name} already up to date: {version}")
                return
            print(f"Current: {current}, upgrading to: {version}")
        except Exception:
            print(f"Could not parse current {name} version, reinstalling...")

    print(f"Installing {name} {version}...")
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
    os_name = {"linux": "linux", "darwin": "darwin"}.get(system)
    if not os_name:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    url = url_template.format(version=version, os=os_name, arch=arch)
    zip_path = Path(f"/tmp/{binary_name}.zip")  # nosec B108

    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, zip_path)  # nosec B310

    install_dir = get_install_dir()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extract(binary_name, install_dir)
    (install_dir / binary_name).chmod(0o755)  # nosec B103
    zip_path.unlink()

    print(f"\u2713 {name} {version} installed.")


def _install_terraform() -> None:
    """Install Terraform."""
    _install_hashicorp_zip(
        name="Terraform",
        repo="hashicorp/terraform",
        url_template=(
            "https://releases.hashicorp.com/terraform/{version}/terraform_{version}_{os}_{arch}.zip"
        ),
        binary_name="terraform",
    )


def _install_opentofu() -> None:
    """Install OpenTofu."""
    _install_hashicorp_zip(
        name="OpenTofu",
        repo="opentofu/opentofu",
        url_template=(
            "https://github.com/opentofu/opentofu/releases/download/"
            "v{version}/tofu_{version}_{os}_{arch}.zip"
        ),
        binary_name="tofu",
    )


def _install_ansible() -> None:
    """Install Ansible via uv."""
    in_venv = (
        os.environ.get("VIRTUAL_ENV")
        or hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    system_flag = "" if in_venv else "--system"

    if os.path.exists("pyproject.toml"):
        print("Installing InfraFoundry with Ansible...")
        subprocess.run(f"uv pip install {system_flag} -e .", shell=True, check=True)  # nosec B602
    else:
        print("Installing Ansible directly...")
        subprocess.run(f"uv pip install {system_flag} ansible", shell=True, check=True)  # nosec B602


# ---------------------------------------------------------------------------
# Doit task definitions
# ---------------------------------------------------------------------------


def task_install_age() -> dict[str, Any]:
    """Install age encryption tool."""
    return {
        "actions": [_install_age],
        "title": title_with_actions,
    }


def task_install_sops() -> dict[str, Any]:
    """Install SOPS secrets manager."""
    return create_install_task(
        name="sops",
        repo="getsops/sops",
        asset_patterns={"linux": "sops-v{version}.linux.amd64"},
        version_cmd=["sops", "--version"],
    )


def task_install_terraform() -> dict[str, Any]:
    """Install Terraform."""
    return {
        "actions": [_install_terraform],
        "title": title_with_actions,
    }


def task_install_opentofu() -> dict[str, Any]:
    """Install OpenTofu."""
    return {
        "actions": [_install_opentofu],
        "title": title_with_actions,
    }


def task_install_ansible() -> dict[str, Any]:
    """Install Ansible via uv."""
    return {
        "actions": [_install_ansible],
        "title": title_with_actions,
    }


def task_install_deps() -> dict[str, Any]:
    """Install all system dependencies."""
    return {
        "actions": [lambda: print("All dependencies installed successfully!")],
        "task_dep": [
            "install_direnv",
            "install_age",
            "install_sops",
            "install_terraform",
            "install_opentofu",
            "install_ansible",
        ],
        "title": title_with_actions,
    }
