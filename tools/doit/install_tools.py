"""InfraFoundry tool installation tasks.

Installs external tools required for infrastructure management:
- direnv: Environment management
- age: Encryption tool
- sops: Secrets management
- terraform: Infrastructure as code
- ansible: Configuration management
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from typing import Any

from doit.tools import title_with_actions


def _run_cmd(cmd: str, shell: bool = True, check: bool = True) -> None:
    """Run a shell command."""
    print(f"Executing: {cmd}")
    subprocess.run(cmd, shell=shell, check=check)


def _get_latest_github_release(repo: str) -> str:
    """Get latest release version from GitHub."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url)

    # Use GitHub token if available to avoid rate limits
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        request.add_header("Authorization", f"token {github_token}")

    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode())
        return data["tag_name"].lstrip("v")


def _install_direnv() -> None:
    """Install direnv."""
    if shutil.which("direnv"):
        print(f"direnv already installed: {subprocess.getoutput('direnv --version')}")
        return

    print("Installing direnv...")
    version = _get_latest_github_release("direnv/direnv")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        bin_url = f"https://github.com/direnv/direnv/releases/download/v{version}/direnv.linux-amd64"
        bin_path = os.path.join(install_dir, "direnv")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)
        _run_cmd(f"chmod +x {bin_path}")
    elif system == "darwin":
        _run_cmd("brew install direnv")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    print("direnv installed. Ensure you have hooked it into your shell.")


def _install_age() -> None:
    """Install age encryption tool."""
    if shutil.which("age"):
        print(f"age already installed: {subprocess.getoutput('age --version')}")
        return

    print("Installing age...")
    version = _get_latest_github_release("FiloSottile/age")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        tar_url = f"https://github.com/FiloSottile/age/releases/download/v{version}/age-v{version}-linux-amd64.tar.gz"
        tar_path = "/tmp/age.tar.gz"
        print(f"Downloading {tar_url}...")
        urllib.request.urlretrieve(tar_url, tar_path)

        import tarfile

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall("/tmp")
        _run_cmd(f"mv /tmp/age/age /tmp/age/age-keygen {install_dir}/")
        _run_cmd(f"chmod +x {install_dir}/age {install_dir}/age-keygen")
        os.remove(tar_path)
        _run_cmd("rm -rf /tmp/age")
    elif system == "darwin":
        _run_cmd("brew install age")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)
    print("age installed")


def _install_sops() -> None:
    """Install SOPS secrets manager."""
    if shutil.which("sops"):
        version_output = subprocess.getoutput("sops --version").splitlines()[0]
        print(f"SOPS already installed: {version_output}")
        return

    print("Installing SOPS...")
    version = _get_latest_github_release("getsops/sops")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        bin_url = f"https://github.com/getsops/sops/releases/download/v{version}/sops-v{version}.linux.amd64"
        bin_path = os.path.join(install_dir, "sops")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)
        _run_cmd(f"chmod +x {bin_path}")
    elif system == "darwin":
        _run_cmd("brew install sops")
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)
    print(f"SOPS {version} installed")


def _install_terraform() -> None:
    """Install Terraform."""
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
                print(f"Terraform already up to date: {latest_version}")
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
    elif machine in ("aarch64", "arm64"):
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
    os.makedirs(install_dir, exist_ok=True)

    print(f"Unzipping to {install_dir}...")
    _run_cmd(f"unzip -o {zip_path} -d {install_dir}")
    _run_cmd(f"chmod +x {install_dir}/terraform")
    os.remove(zip_path)
    print(f"Terraform {latest_version} installed to {install_dir}")


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
        _run_cmd(f"uv pip install {system_flag} -e .")
    else:
        print("Installing Ansible directly...")
        _run_cmd(f"uv pip install {system_flag} ansible")


def task_install_direnv() -> dict[str, Any]:
    """Install direnv environment manager."""
    return {
        "actions": [_install_direnv],
        "title": title_with_actions,
    }


def task_install_age() -> dict[str, Any]:
    """Install age encryption tool."""
    return {
        "actions": [_install_age],
        "title": title_with_actions,
    }


def task_install_sops() -> dict[str, Any]:
    """Install SOPS secrets manager."""
    return {
        "actions": [_install_sops],
        "title": title_with_actions,
    }


def task_install_terraform() -> dict[str, Any]:
    """Install Terraform."""
    return {
        "actions": [_install_terraform],
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
            "install_ansible",
        ],
        "title": title_with_actions,
    }
