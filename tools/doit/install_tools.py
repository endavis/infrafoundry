"""InfraFoundry tool installation tasks.

Extends the reusable GitHub release install framework with
project-specific tools: age, sops, terraform, opentofu, ansible.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess  # nosec B404 - subprocess is required for version checks
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from doit.tools import title_with_actions

# Hosts whose release assets we fetch without a caller-supplied digest.
#
# This is not a claim that GitHub is trustworthy in some absolute sense — it is
# the same trust already extended by cloning this template. What it excludes is
# the `url_template` escape hatch (ADR-9015), which exists precisely to fetch
# from arbitrary third parties such as `releases.hashicorp.com`. Those bypass
# even that implicit trust, so they must name what they expect to receive.
IMPLICITLY_TRUSTED_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "raw.githubusercontent.com",
        "api.github.com",
    }
)

_DIGEST_CHUNK = 1024 * 1024


class IntegrityError(RuntimeError):
    """A download did not match the digest the caller expected."""


def sha256_of(path: Path) -> str:
    """Return the lowercase hex SHA-256 of the file at *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def requires_digest(url: str) -> bool:
    """Return whether *url* must be accompanied by an expected digest.

    True for any host outside :data:`IMPLICITLY_TRUSTED_HOSTS` — the
    ``url_template`` escape hatch added in ADR-9015.
    """
    return (urlparse(url).hostname or "").lower() not in IMPLICITLY_TRUSTED_HOSTS


def verify_download(path: Path, url: str, expected_sha256: str | None) -> None:
    """Verify *path* against *expected_sha256*, deleting it if it does not match.

    Fails closed in both directions:

    - A digest that does not match aborts and leaves nothing on disk, so a
      failed verification can never be mistaken for a completed install.
    - A download from an untrusted host with no expected digest aborts before
      the file is ever made executable.

    Args:
        path: The downloaded file.
        url: Where it came from, used to decide whether a digest is mandatory.
        expected_sha256: The hex digest the caller expects, if any.

    Raises:
        IntegrityError: On mismatch, or when a digest is required and absent.
    """
    if expected_sha256 is None:
        if requires_digest(url):
            path.unlink(missing_ok=True)
            raise IntegrityError(
                f"{url} is outside {sorted(IMPLICITLY_TRUSTED_HOSTS)} and no sha256 was "
                "given. Pass sha256= to install_tool()/create_install_task() naming the "
                "digest you expect (see docs/development/install-tools-framework.md)."
            )
        return

    actual = sha256_of(path)
    if actual.lower() != expected_sha256.strip().lower():
        path.unlink(missing_ok=True)
        raise IntegrityError(
            f"Integrity check failed for {url}\n"
            f"  expected sha256: {expected_sha256.strip().lower()}\n"
            f"  actual sha256:   {actual}\n"
            "The downloaded file has been deleted. Nothing was installed."
        )


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


def fetch_sha256_from_sums(sums_url: str, filename: str) -> str:
    """Look up *filename*'s digest in a ``SHA256SUMS``-style checksums file.

    Publishers outside GitHub (e.g. ``releases.hashicorp.com``) ship one per
    release, with lines of the form ``<hex digest>  <filename>``. The digest is
    then passed as ``sha256=`` so the archive is verified before extraction.

    Args:
        sums_url: URL of the checksums file.
        filename: Archive basename to look up.

    Returns:
        The lowercase hex SHA-256 digest for *filename*.

    Raises:
        IntegrityError: If *filename* is not listed in the checksums file.
    """
    with urllib.request.urlopen(sums_url) as response:  # nosec B310 - hardcoded release host
        sums = response.read().decode()
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    raise IntegrityError(f"{filename} is not listed in {sums_url}")


def get_install_dir() -> Path:
    """Get the standard installation directory for user-local binaries.

    Returns:
        Path to ~/.local/bin, created if it does not exist.
    """
    install_dir = Path.home() / ".local" / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)
    return install_dir


def _get_arch() -> str:
    """Map platform.machine() output to a normalized architecture name.

    Returns:
        "amd64" for x86_64, "arm64" for aarch64, otherwise the raw machine
        name lowercased (passthrough).
    """
    machine = platform.machine().lower()
    if machine == "x86_64":
        return "amd64"
    if machine == "aarch64":
        return "arm64"
    return machine


def _build_github_release_url(repo: str, version: str, asset_pattern: str) -> str:
    """Build a GitHub release asset download URL.

    Args:
        repo: GitHub repository in "owner/name" format.
        version: Release version (without leading 'v').
        asset_pattern: Filename pattern with optional {version} placeholder.

    Returns:
        Fully constructed download URL.
    """
    asset_name = asset_pattern.format(version=version)
    return f"https://github.com/{repo}/releases/download/v{version}/{asset_name}"


def download_github_release_binary(
    repo: str, version: str, asset_pattern: str, dest_name: str, sha256: str | None = None
) -> Path:
    """Download a binary asset from a GitHub release.

    Constructs the download URL from the repo, version, and asset pattern,
    downloads the file to the user-local bin directory, and makes it
    executable.

    Args:
        repo: GitHub repository in "owner/name" format.
        version: Release version (without leading 'v').
        asset_pattern: Filename pattern with {version} placeholder
            (e.g. "tool.linux-amd64" or "tool-v{version}-linux-amd64").
        dest_name: Name of the installed binary (e.g. "tool").
        sha256: Expected hex SHA-256 of the asset. Optional for GitHub hosts;
            verified when given.

    Returns:
        Path to the downloaded and installed binary.

    Raises:
        IntegrityError: If the download does not match *sha256*.
    """
    url = _build_github_release_url(repo, version, asset_pattern)
    install_dir = get_install_dir()
    dest_path = install_dir / dest_name

    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, dest_path)  # nosec B310 - GitHub release URL; integrity via verify_download below
    # Verify before the executable bit goes on: a file that never becomes
    # executable cannot be run by a caller that ignores the exception.
    verify_download(dest_path, url, sha256)
    dest_path.chmod(0o755)  # nosec B103 - rwxr-xr-x is required for executable binary

    return dest_path


def download_and_extract_archive(
    url: str, extract_binaries: list[str], dest_dir: Path, sha256: str | None = None
) -> list[Path]:
    """Download an archive and extract specific binaries from it.

    Supports `.tar.gz`/`.tgz` and `.zip` archives. Binaries are matched by
    basename (any directory structure inside the archive is ignored).
    Each extracted file is made executable (0o755).

    Security:
        - Tar archives use ``tarfile.data_filter`` (Python 3.12+) when
          available to block path traversal, symlinks, etc.
        - Zip archives use basename-only extraction with a defense-in-depth
          zip-slip resolve check.

    Args:
        url: URL to download the archive from. Format is detected from
            the URL extension.
        extract_binaries: List of binary basenames to extract from the
            archive (e.g. ``["age", "age-keygen"]``).
        dest_dir: Directory to write extracted binaries into. Created if
            it does not exist.
        sha256: Expected hex SHA-256 of the archive. Mandatory when *url* is
            outside :data:`IMPLICITLY_TRUSTED_HOSTS`; optional otherwise.

    Returns:
        List of Paths to the extracted binaries.

    Raises:
        ValueError: If the URL has an unsupported archive extension.
        RuntimeError: If a requested binary is not found in the archive.
        IntegrityError: If the archive does not match *sha256*, or a digest is
            required for this host and none was given. Verified before the
            archive is opened, so an unverified archive is never parsed.
    """
    url_lower = url.lower()
    if url_lower.endswith((".tar.gz", ".tgz")):
        suffix = ".tar.gz"
        archive_kind = "tar"
    elif url_lower.endswith(".zip"):
        suffix = ".zip"
        archive_kind = "zip"
    else:
        raise ValueError(f"Unsupported archive extension: {url}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(extract_binaries)
    extracted: dict[str, Path] = {}

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = Path(tmp.name)
    try:
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, temp_path)  # nosec B310 - integrity via verify_download below, before the archive is opened
        # Before opening the archive: extraction hardening (data_filter, zip-slip
        # checks) limits what a malicious archive can write, but parsing one at
        # all is avoidable when we already know it is the wrong bytes.
        verify_download(temp_path, url, sha256)

        if archive_kind == "tar":
            with tarfile.open(temp_path, "r:gz") as tar:  # nosec B202 - data_filter set below when available
                if hasattr(tarfile, "data_filter"):
                    tar.extraction_filter = tarfile.data_filter
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    basename = Path(member.name).name
                    if basename not in wanted or basename in extracted:
                        continue
                    src = tar.extractfile(member)
                    if src is None:
                        continue
                    out_path = dest_dir / basename
                    with open(out_path, "wb") as out:
                        shutil.copyfileobj(src, out)
                    out_path.chmod(0o755)  # nosec B103 - executable bit required
                    extracted[basename] = out_path
        else:  # zip
            with zipfile.ZipFile(temp_path) as zf:
                for entry in zf.namelist():
                    if entry.endswith("/"):
                        continue
                    basename = Path(entry).name
                    if basename not in wanted or basename in extracted:
                        continue
                    out_path = dest_dir / basename
                    # Defense in depth against zip-slip; basename-only
                    # extraction already prevents traversal.
                    resolved = out_path.resolve()
                    if not str(resolved).startswith(str(dest_dir.resolve())):
                        raise RuntimeError(f"Refusing to extract outside dest_dir: {entry}")
                    data = zf.read(entry)
                    out_path.write_bytes(data)
                    out_path.chmod(0o755)  # nosec B103 - executable bit required
                    extracted[basename] = out_path

        missing = [b for b in extract_binaries if b not in extracted]
        if missing:
            raise RuntimeError(f"Binary {missing[0]} not found in archive")

        return [extracted[b] for b in extract_binaries]
    finally:
        if temp_path.exists():
            temp_path.unlink()


def install_tool(
    name: str,
    repo: str,
    asset_patterns: dict[str, str],
    version_cmd: list[str] | None = None,
    post_install_message: str | None = None,
    extract_binaries: list[str] | dict[str, list[str]] | None = None,
    url_template: str | None = None,
    prefer_brew: bool = True,
    sha256: str | dict[str, str] | None = None,
) -> None:
    """Install a tool from GitHub releases if not already present.

    Checks if the tool is already on PATH. If so, prints its version
    and returns. Otherwise, downloads the latest release for the current
    platform and installs it.

    Args:
        name: Tool name used for PATH lookup and as the binary dest name.
        repo: GitHub repository in "owner/name" format.
        asset_patterns: Mapping of platform.system().lower() values
            (e.g. "linux", "darwin") to asset filename patterns.
            Patterns may include a {version} placeholder.
        version_cmd: Command list to run for checking installed version
            (e.g. ["tool", "--version"]). Defaults to [name, "--version"].
        post_install_message: Optional message printed after installation.
        extract_binaries: Optional list of binary basenames to extract from
            a downloaded archive (e.g. ``["age", "age-keygen"]``). When set,
            the download is treated as an archive (`.tar.gz`/`.tgz`/`.zip`)
            and binaries are extracted into the install dir.

            Also accepts a per-platform mapping using the same key
            convention as ``asset_patterns`` (``platform.system().lower()``
            values such as ``"linux"``, ``"darwin"``, ``"windows"``).
            Use this when archive members differ per OS — for example,
            when Windows builds add a ``.exe`` suffix::

                extract_binaries={
                    "linux": ["age", "age-keygen"],
                    "darwin": ["age", "age-keygen"],
                    "windows": ["age.exe", "age-keygen.exe"],
                }

            On a platform missing from the dict, the install aborts with
            the same ``Unsupported OS`` error used for ``asset_patterns``.
        url_template: Optional download URL template with ``{version}``,
            ``{os}``, and ``{arch}`` placeholders. When set, this is used
            instead of building a GitHub release URL from ``asset_patterns``.
        prefer_brew: When True (the default), use ``brew install`` on macOS
            instead of downloading. Set False to force download even on
            macOS (useful for cross-platform consistency).
        sha256: Expected hex SHA-256 of the downloaded asset. Either a single
            digest, or a per-platform mapping keyed like ``asset_patterns``
            (``platform.system().lower()``) for tools whose asset differs per
            OS. Mandatory when the resolved URL is outside
            :data:`IMPLICITLY_TRUSTED_HOSTS` — the ``url_template`` escape
            hatch from ADR-9015 reaches arbitrary third parties, so those must
            name what they expect to receive.

    Raises:
        IntegrityError: If the download does not match *sha256*, or a digest is
            required for the resolved host and none was given. Nothing is left
            on disk and nothing is made executable.
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
        print(f"[OK] {name} already installed: {version_output}")
        return

    print(f"Installing {name}...")
    version = get_latest_github_release(repo)
    print(f"Latest version: {version}")

    system = platform.system().lower()
    expected_sha = sha256.get(system) if isinstance(sha256, dict) else sha256

    if system == "darwin" and prefer_brew and url_template is None:
        subprocess.run(["brew", "install", name], check=True)
    else:
        if url_template is not None:
            url = url_template.format(version=version, os=system, arch=_get_arch())
        elif system in asset_patterns:
            url = _build_github_release_url(repo, version, asset_patterns[system])
        else:
            print(f"Unsupported OS for {name}: {system}")
            sys.exit(1)

        if extract_binaries:
            if isinstance(extract_binaries, dict):
                if system not in extract_binaries:
                    print(f"Unsupported OS for {name}: {system}")
                    sys.exit(1)
                resolved_binaries = extract_binaries[system]
            else:
                resolved_binaries = extract_binaries
            download_and_extract_archive(url, resolved_binaries, get_install_dir(), expected_sha)
        else:
            if url_template is not None:
                install_dir = get_install_dir()
                dest_path = install_dir / name
                print(f"Downloading {url}...")
                urllib.request.urlretrieve(url, dest_path)  # nosec B310 - integrity via verify_download below, before chmod
                verify_download(dest_path, url, expected_sha)
                dest_path.chmod(0o755)  # nosec B103 - executable bit required
            else:
                download_github_release_binary(
                    repo=repo,
                    version=version,
                    asset_pattern=asset_patterns[system],
                    dest_name=name,
                    sha256=expected_sha,
                )

    print(f"[OK] {name} installed.")
    if post_install_message:
        print(post_install_message)


def create_install_task(
    name: str,
    repo: str,
    asset_patterns: dict[str, str],
    version_cmd: list[str] | None = None,
    post_install_message: str | None = None,
    extract_binaries: list[str] | dict[str, list[str]] | None = None,
    url_template: str | None = None,
    prefer_brew: bool = True,
    sha256: str | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a doit task dict for installing a tool from GitHub releases.

    This is a factory function that returns a doit-compatible task
    dictionary. The task's action calls install_tool with the provided
    parameters.

    Args:
        name: Tool name used for PATH lookup and as the binary dest name.
        repo: GitHub repository in "owner/name" format.
        asset_patterns: Mapping of platform names to asset filename patterns.
        version_cmd: Command list for version check. Defaults to [name, "--version"].
        post_install_message: Optional message printed after installation.
        extract_binaries: Optional list of binary basenames to extract from
            a downloaded archive, or a per-platform mapping keyed by
            ``platform.system().lower()`` (e.g. ``{"linux": ["age"],
            "windows": ["age.exe"]}``) when archive members differ per OS.
            See :func:`install_tool`.
        url_template: Optional download URL template with ``{version}``,
            ``{os}``, ``{arch}`` placeholders. See :func:`install_tool`.
        prefer_brew: Use brew on macOS when True (default). See
            :func:`install_tool`.
        sha256: Expected hex SHA-256 of the asset, or a per-platform mapping.
            Mandatory for URLs outside :data:`IMPLICITLY_TRUSTED_HOSTS`. See
            :func:`install_tool`.

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
            extract_binaries=extract_binaries,
            url_template=url_template,
            prefer_brew=prefer_brew,
            sha256=sha256,
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
        print(f"✓ age already installed: {result.stdout.strip()}")
        return

    print("Installing age...")
    version = get_latest_github_release("FiloSottile/age")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    if system == "darwin":
        subprocess.run(["brew", "install", "age"], check=True)
    elif system == "linux":
        arch = _get_arch()
        tar_url = (
            f"https://github.com/FiloSottile/age/releases/download/"
            f"v{version}/age-v{version}-linux-{arch}.tar.gz"
        )
        download_and_extract_archive(tar_url, ["age", "age-keygen"], get_install_dir())
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    print("✓ age installed.")


def _install_hashicorp_zip(
    name: str,
    repo: str,
    url_template: str,
    binary_name: str | None = None,
    sums_url_template: str | None = None,
) -> None:
    """Install a HashiCorp-style tool distributed as a zip archive.

    Args:
        name: Display name (e.g. "Terraform").
        repo: GitHub repo for version lookup.
        url_template: Download URL with {version}, {os}, {arch} placeholders.
        binary_name: Binary name inside zip (defaults to lowercase name).
        sums_url_template: Checksums-file URL with a {version} placeholder. Required
            when *url_template* is outside the implicitly trusted GitHub hosts, since
            the download must then be verified against a digest.
    """
    if binary_name is None:
        binary_name = name.lower()

    version = get_latest_github_release(repo)

    if shutil.which(binary_name):
        # B605: binary_name is a hardcoded tool name verified via shutil.which()
        # before invocation; no user input flows into the command string.
        version_json = subprocess.getoutput(f"{binary_name} version -json")  # nosec B605
        try:
            current = json.loads(version_json)["terraform_version"]
            if current == version:
                print(f"✓ {name} already up to date: {version}")
                return
            print(f"Current: {current}, upgrading to: {version}")
        except Exception:
            print(f"Could not parse current {name} version, reinstalling...")

    print(f"Installing {name} {version}...")
    system = platform.system().lower()
    arch = _get_arch()
    os_name = {"linux": "linux", "darwin": "darwin"}.get(system)
    if not os_name:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    url = url_template.format(version=version, os=os_name, arch=arch)
    sha256 = None
    if sums_url_template is not None:
        sha256 = fetch_sha256_from_sums(
            sums_url_template.format(version=version), url.rsplit("/", 1)[-1]
        )
    download_and_extract_archive(url, [binary_name], get_install_dir(), sha256=sha256)

    print(f"✓ {name} {version} installed.")


def _install_terraform() -> None:
    """Install Terraform."""
    _install_hashicorp_zip(
        name="Terraform",
        repo="hashicorp/terraform",
        url_template=(
            "https://releases.hashicorp.com/terraform/{version}/terraform_{version}_{os}_{arch}.zip"
        ),
        binary_name="terraform",
        sums_url_template=(
            "https://releases.hashicorp.com/terraform/{version}/terraform_{version}_SHA256SUMS"
        ),
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
