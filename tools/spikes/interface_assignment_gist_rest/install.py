"""Idempotent installer for the AssignSettingsController.php fork on OPNsense.

This script SCPs the controller to the OPNsense MVC controllers directory,
restarts the configd + php_fpm services so the MVC layer re-discovers the
new controller, and verifies the on-box checksum matches the local file.

It is **idempotent**: re-running with no changes is a no-op (checksum match
short-circuits the SCP+restart path).

Environment variable contract::

    OPNSENSE_SSH_HOST         — defaults to the host part of OPNSENSE_API_URL
    OPNSENSE_SSH_USER         — defaults to "root"
    OPNSENSE_SSH_PORT         — defaults to "22"
    OPNSENSE_SSH_KEY          — optional, path to the SSH private key.
                                 If unset, ssh-agent and ~/.ssh/config provide
                                 the identity. The script never prompts.
    OPNSENSE_INSTALL_PATH     — defaults to the canonical MVC path

The shell utilities ``ssh`` and ``scp`` must be on ``PATH``; they are invoked
via ``subprocess.run`` with ``shell=False`` and an explicit argument list.

Usage::

    # Standalone install:
    python tools/spikes/interface_assignment_gist_rest/install.py install

    # Verify the on-box file checksum matches the local source:
    python tools/spikes/interface_assignment_gist_rest/install.py verify

This module is designed to be importable so the spike's ``inspect`` subcommand
can call ``verify_installed_checksum()`` directly without shelling out to a
separate script.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_INSTALL_PATH = (
    "/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php"
)
CONTROLLER_FILENAME = "AssignSettingsController.php"


@dataclass(frozen=True)
class SshTarget:
    """Connection details for the OPNsense box."""

    host: str
    user: str
    port: int
    key_path: Path | None  # None → rely on ssh-agent / ~/.ssh/config
    install_path: str

    @property
    def remote(self) -> str:
        """``user@host`` form for ``ssh``/``scp``."""
        return f"{self.user}@{self.host}"


def load_ssh_target(env: dict[str, str] | None = None) -> SshTarget:
    """Read SSH connection details from environment variables.

    ``OPNSENSE_SSH_HOST`` falls back to the host part of ``OPNSENSE_API_URL``
    when unset — common case where a single env defines both REST and SSH
    targets. ``OPNSENSE_SSH_KEY`` is optional; when unset, ssh-agent and
    ``~/.ssh/config`` provide the identity.

    Args:
        env: Mapping to read from. Defaults to ``os.environ``.

    Returns:
        A populated ``SshTarget``.

    Raises:
        RuntimeError: If neither ``OPNSENSE_SSH_HOST`` nor ``OPNSENSE_API_URL``
            is set, or if a supplied ``OPNSENSE_SSH_KEY`` path does not exist.
    """
    source: dict[str, str] = dict(os.environ if env is None else env)

    host = source.get("OPNSENSE_SSH_HOST", "").strip()
    if not host:
        api_url = source.get("OPNSENSE_API_URL", "").strip()
        if api_url:
            host = (urlparse(api_url).hostname or "").strip()
    if not host:
        raise RuntimeError("OPNSENSE_SSH_HOST is required (or set OPNSENSE_API_URL to derive it).")

    key_str = source.get("OPNSENSE_SSH_KEY", "").strip()
    key_path: Path | None = None
    if key_str:
        key_path = Path(key_str).expanduser()
        if not key_path.exists():
            raise RuntimeError(f"SSH key does not exist: {key_path}")

    user = source.get("OPNSENSE_SSH_USER", "root").strip() or "root"
    port_raw = source.get("OPNSENSE_SSH_PORT", "22").strip() or "22"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"OPNSENSE_SSH_PORT must be an integer, got: {port_raw!r}") from exc

    install_path = source.get("OPNSENSE_INSTALL_PATH", "").strip() or DEFAULT_INSTALL_PATH

    return SshTarget(
        host=host,
        user=user,
        port=port,
        key_path=key_path,
        install_path=install_path,
    )


def local_controller_path() -> Path:
    """Return the path to the bundled controller PHP source."""
    return Path(__file__).resolve().parent / CONTROLLER_FILENAME


def compute_local_checksum(path: Path) -> str:
    """SHA-256 of a local file, as a hex string."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _identity_args(target: SshTarget) -> list[str]:
    """Return ``["-i", "<path>"]`` when an explicit key is configured, else ``[]``.

    With an empty list the system ssh client falls back to ssh-agent and
    ``~/.ssh/config`` for the identity — the typical homelab setup.
    """
    if target.key_path is None:
        return []
    return ["-i", str(target.key_path)]


def _ssh_args(target: SshTarget) -> list[str]:
    """Common ssh args for non-interactive use."""
    return [
        "ssh",
        *_identity_args(target),
        "-p",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        target.remote,
    ]


def _scp_args(target: SshTarget, source_path: Path, remote_path: str) -> list[str]:
    """Build an SCP argv that transfers a single file."""
    return [
        "scp",
        *_identity_args(target),
        "-P",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        str(source_path),
        f"{target.remote}:{remote_path}",
    ]


def _run(argv: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    """Wrapper around subprocess.run with consistent defaults.

    ``shell=False`` always; argv is a list. Captures stdout/stderr by default.
    """
    return subprocess.run(
        argv,
        capture_output=capture_output,
        check=False,
        text=True,
    )


def fetch_remote_checksum(target: SshTarget) -> str | None:
    """Compute the SHA-256 checksum of the controller currently on the box.

    Returns ``None`` if the file doesn't exist on the remote (i.e., never
    installed). Raises if the SSH command itself fails for some other reason.

    OPNsense's default root shell is ``opnsense-shell`` (csh-derived), where
    ``2>/dev/null`` is "Ambiguous output redirect." We avoid stderr redirection
    entirely by guarding with ``test -f`` (portable across both shells); if
    the file is missing the guard short-circuits and the chained ``echo
    MISSING`` runs, otherwise ``sha256 -q`` produces the hash on stdout.
    """
    cmd = [
        *_ssh_args(target),
        f"test -f {target.install_path} && sha256 -q {target.install_path} || echo MISSING",
    ]
    result = _run(cmd)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"SSH probe failed (rc={result.returncode}): {err}")
    out = result.stdout.strip()
    if out == "MISSING" or out == "":
        return None
    return out


def verify_installed_checksum(target: SshTarget | None = None) -> tuple[bool, str | None, str]:
    """Compare the on-box controller's SHA-256 to the local source.

    Args:
        target: Connection details. If ``None``, reads from env.

    Returns:
        ``(matches, remote_sum, local_sum)``. ``matches`` is ``False`` if
        the file is missing on the remote or differs from local.
    """
    if target is None:
        target = load_ssh_target()
    local_sum = compute_local_checksum(local_controller_path())
    remote_sum = fetch_remote_checksum(target)
    matches = remote_sum == local_sum
    return matches, remote_sum, local_sum


def install_controller(target: SshTarget | None = None, *, force: bool = False) -> bool:
    """SCP the controller, restart services, verify checksum.

    Args:
        target: Connection details. If ``None``, reads from env.
        force: If True, re-install even when the on-box checksum already
            matches. Useful for forcing a service restart.

    Returns:
        ``True`` if the controller was (re)installed; ``False`` if it was
        already current and no install was needed.
    """
    if target is None:
        target = load_ssh_target()

    local_path = local_controller_path()
    if not local_path.exists():
        raise RuntimeError(f"Local controller not found: {local_path}")

    matches, remote_sum, local_sum = verify_installed_checksum(target)
    if matches and not force:
        print(f"Controller already current on {target.host} (sha256 {local_sum[:12]}…). Skipping.")
        return False

    if remote_sum is None:
        print(f"Controller not present on {target.host}. Installing fresh.")
    else:
        print(
            f"Controller checksum mismatch on {target.host} "
            f"(remote {remote_sum[:12]}…, local {local_sum[:12]}…). Replacing."
        )

    # Step 1: SCP the file.
    scp_cmd = _scp_args(target, local_path, target.install_path)
    print(f"Running: {' '.join(scp_cmd)}")
    scp_result = _run(scp_cmd)
    if scp_result.returncode != 0:
        raise RuntimeError(
            f"SCP failed (rc={scp_result.returncode}): "
            f"{scp_result.stderr.strip() or scp_result.stdout.strip()}"
        )

    # Step 2: Permissions + ownership. OPNsense controllers run as root:wheel
    # readable by the php_fpm pool; we set 0644 so the GUI's MVC autoloader
    # can read them.
    chmod_cmd = [*_ssh_args(target), f"chmod 0644 {target.install_path}"]
    chmod_result = _run(chmod_cmd)
    if chmod_result.returncode != 0:
        raise RuntimeError(f"chmod failed: {chmod_result.stderr.strip()}")

    # Step 3: Restart configd + php_fpm so the MVC layer re-discovers the controller.
    # OPNsense's `service` command works for both. We restart configd first;
    # php_fpm second so any in-flight GUI request sees the new controller.
    for service_name in ("configd", "php_fpm"):
        restart_cmd = [*_ssh_args(target), f"service {service_name} restart"]
        rc = _run(restart_cmd)
        if rc.returncode != 0:
            raise RuntimeError(
                f"service {service_name} restart failed (rc={rc.returncode}): "
                f"{rc.stderr.strip() or rc.stdout.strip()}"
            )
        print(f"Restarted service: {service_name}")

    # Step 4: Verify post-install checksum.
    matches_after, remote_after, _ = verify_installed_checksum(target)
    if not matches_after:
        raise RuntimeError(
            f"Post-install checksum mismatch on {target.host}: "
            f"remote {remote_after}, local {local_sum}. Install may have failed silently."
        )
    print(f"Install verified on {target.host}: sha256 {local_sum[:12]}…")
    return True


def _ensure_ssh_tools_present() -> None:
    """Fail loudly if ``ssh``/``scp`` aren't on ``PATH``."""
    missing: list[str] = [tool for tool in ("ssh", "scp") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Required SSH tool(s) not on PATH: {', '.join(missing)}. "
            "Install OpenSSH client utilities."
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="install_assign_settings_controller",
        description="Install/verify the AssignSettingsController.php fork on OPNsense.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    install_parser = sub.add_parser("install", help="SCP + service restart + verify.")
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-install even when the on-box checksum already matches.",
    )
    sub.add_parser("verify", help="Just compare the on-box checksum to the local source.")

    args = parser.parse_args(argv)

    _ensure_ssh_tools_present()

    target = load_ssh_target()

    if args.command == "install":
        install_controller(target, force=bool(args.force))
        return 0

    if args.command == "verify":
        matches, remote_sum, local_sum = verify_installed_checksum(target)
        local_short = local_sum[:12]
        if matches:
            print(f"OK: on-box and local checksums match (sha256 {local_short}…).")
            return 0
        if remote_sum is None:
            print(f"MISSING: controller not installed on {target.host}.")
        else:
            print(f"MISMATCH: remote {remote_sum[:12]}… vs local {local_short}…")
        return 1

    parser.error(f"Unknown command: {args.command}")  # NoReturn


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
