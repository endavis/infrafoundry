"""Idempotent installer for the AssignSettingsController.php fork on OPNsense.

This module SCPs the controller PHP to the OPNsense MVC controllers
directory, restarts the configd + php_fpm services so the MVC layer
re-discovers the new controller, and verifies the on-box checksum
matches the local file.

The public entry point is ``ensure_installed(target=None)``. It is
**idempotent**: when the on-box file checksum matches the local source
the call short-circuits to ``False`` (no SCP, no restart) — the typical
case on every ``InterfaceAssignmentManager.apply()`` after the first
deploy. On checksum mismatch (or first install) it SCPs the file,
fixes permissions, restarts both daemons, and re-verifies before
returning ``True``.

Environment variable contract::

    OPNSENSE_SSH_HOST         — defaults to the host part of OPNSENSE_API_URL
    OPNSENSE_SSH_USER         — defaults to "root"
    OPNSENSE_SSH_PORT         — defaults to "22"
    OPNSENSE_SSH_KEY          — optional, path to the SSH private key.
                                 If unset, ssh-agent and ~/.ssh/config
                                 provide the identity.
    OPNSENSE_INSTALL_PATH     — defaults to the canonical MVC path

The shell utilities ``ssh`` and ``scp`` must be on ``PATH``; they are
invoked via ``subprocess.run`` with ``shell=False`` and an explicit
argument list (no command injection surface).

Lifted from the spike at ``tools/spikes/interface_assignment_gist_rest/
install.py``; the standalone ``argparse`` CLI was dropped because in
production the installer is driven by ``InterfaceAssignmentManager.
apply()`` (manager-level installer integration per #720 plan).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess  # nosec B404 - required for SCP + SSH to OPNsense for one-time controller install
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_INSTALL_PATH = (
    "/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php"
)
CONTROLLER_FILENAME = "AssignSettingsController.php"


@dataclass(frozen=True)
class SshTarget:
    """Connection details for the OPNsense box.

    Attributes:
        host: Hostname or IP of the OPNsense box.
        user: SSH user (defaults to ``root``).
        port: SSH port (defaults to ``22``).
        key_path: Path to private key, or ``None`` to fall back to
            ssh-agent / ``~/.ssh/config``.
        install_path: Absolute path on the box where the controller
            PHP file lives.
    """

    host: str
    user: str
    port: int
    key_path: Path | None
    install_path: str

    @property
    def remote(self) -> str:
        """Return ``user@host`` form for ``ssh``/``scp``."""
        return f"{self.user}@{self.host}"


def load_ssh_target(env: dict[str, str] | None = None) -> SshTarget:
    """Read SSH connection details from environment variables.

    ``OPNSENSE_SSH_HOST`` falls back to the host part of
    ``OPNSENSE_API_URL`` when unset — common case where a single env
    defines both REST and SSH targets. ``OPNSENSE_SSH_KEY`` is
    optional; when unset, ssh-agent and ``~/.ssh/config`` provide the
    identity.

    Args:
        env: Mapping to read from. Defaults to ``os.environ``.
            Injectable for tests.

    Returns:
        A populated ``SshTarget``.

    Raises:
        RuntimeError: If neither ``OPNSENSE_SSH_HOST`` nor
            ``OPNSENSE_API_URL`` is set, the configured port is not an
            integer, or a supplied ``OPNSENSE_SSH_KEY`` path does not
            exist.
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
    """Return the SHA-256 hex digest of a local file.

    Args:
        path: File whose contents to hash.

    Returns:
        Lowercase hex string with no separator characters.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _identity_args(target: SshTarget) -> list[str]:
    """Return ``["-i", "<path>"]`` when an explicit key is configured, else ``[]``.

    With an empty list the system ssh client falls back to ssh-agent
    and ``~/.ssh/config`` for the identity — the typical homelab
    setup.
    """
    if target.key_path is None:
        return []
    return ["-i", str(target.key_path)]


def _ssh_args(target: SshTarget) -> list[str]:
    """Return common ssh args for non-interactive use."""
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
    """Wrap ``subprocess.run`` with consistent defaults.

    ``shell=False`` always; argv is a list. Captures stdout/stderr by
    default so callers can surface failure context.
    """
    return subprocess.run(
        argv,
        capture_output=capture_output,
        check=False,
        text=True,
    )


def fetch_remote_checksum(target: SshTarget) -> str | None:
    """Compute the SHA-256 checksum of the controller currently on the box.

    Returns ``None`` if the file doesn't exist on the remote (i.e.,
    never installed). Raises if the SSH command itself fails for some
    other reason.

    OPNsense's default root shell is ``opnsense-shell`` (csh-derived),
    where ``2>/dev/null`` is "Ambiguous output redirect." We avoid
    stderr redirection entirely by guarding with ``test -f`` (portable
    across both shells); if the file is missing the guard
    short-circuits and the chained ``echo MISSING`` runs, otherwise
    ``sha256 -q`` produces the hash on stdout.

    Args:
        target: Connection details.

    Returns:
        Hex digest string when present, ``None`` when the controller
        is missing on the remote.

    Raises:
        RuntimeError: If the SSH probe itself fails.
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
        ``(matches, remote_sum, local_sum)``. ``matches`` is ``False``
        if the file is missing on the remote or differs from local.
    """
    if target is None:
        target = load_ssh_target()
    local_sum = compute_local_checksum(local_controller_path())
    remote_sum = fetch_remote_checksum(target)
    matches = remote_sum == local_sum
    return matches, remote_sum, local_sum


def install_controller(target: SshTarget | None = None, *, force: bool = False) -> bool:
    """SCP the controller, restart services, verify checksum.

    Idempotent: a second call with no changes short-circuits via the
    pre-install checksum probe.

    Args:
        target: Connection details. If ``None``, reads from env.
        force: If ``True``, re-install even when the on-box checksum
            already matches. Useful for forcing a service restart.

    Returns:
        ``True`` if the controller was (re)installed; ``False`` if it
        was already current and no install was needed.

    Raises:
        RuntimeError: If the local controller file is missing, SCP
            fails, the chmod or service-restart commands fail, or the
            post-install checksum does not match the source.
    """
    if target is None:
        target = load_ssh_target()

    local_path = local_controller_path()
    if not local_path.exists():
        raise RuntimeError(f"Local controller not found: {local_path}")

    matches, remote_sum, local_sum = verify_installed_checksum(target)
    if matches and not force:
        return False

    # Step 1: SCP the file.
    scp_cmd = _scp_args(target, local_path, target.install_path)
    scp_result = _run(scp_cmd)
    if scp_result.returncode != 0:
        raise RuntimeError(
            f"SCP failed (rc={scp_result.returncode}): "
            f"{scp_result.stderr.strip() or scp_result.stdout.strip()}"
        )

    # Step 2: Permissions + ownership. OPNsense controllers run as
    # root:wheel, readable by the php_fpm pool; we set 0644 so the
    # GUI's MVC autoloader can read them.
    chmod_cmd = [*_ssh_args(target), f"chmod 0644 {target.install_path}"]
    chmod_result = _run(chmod_cmd)
    if chmod_result.returncode != 0:
        raise RuntimeError(f"chmod failed: {chmod_result.stderr.strip()}")

    # Step 3: Restart configd + php_fpm so the MVC layer re-discovers
    # the controller. We restart configd first; php_fpm second so any
    # in-flight GUI request sees the new controller.
    for service_name in ("configd", "php_fpm"):
        restart_cmd = [*_ssh_args(target), f"service {service_name} restart"]
        rc = _run(restart_cmd)
        if rc.returncode != 0:
            raise RuntimeError(
                f"service {service_name} restart failed (rc={rc.returncode}): "
                f"{rc.stderr.strip() or rc.stdout.strip()}"
            )

    # Step 4: Verify post-install checksum.
    matches_after, remote_after, _ = verify_installed_checksum(target)
    if not matches_after:
        raise RuntimeError(
            f"Post-install checksum mismatch on {target.host}: "
            f"remote {remote_after}, local {local_sum}. Install may have failed silently."
        )
    # Read but ignore — kept so callers/tests can pattern-match the
    # pre-install state if needed.
    _ = remote_sum
    return True


def _ensure_ssh_tools_present() -> None:
    """Fail loudly if ``ssh``/``scp`` aren't on ``PATH``."""
    missing: list[str] = [tool for tool in ("ssh", "scp") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Required SSH tool(s) not on PATH: {', '.join(missing)}. "
            "Install OpenSSH client utilities."
        )


def ensure_installed(target: SshTarget | None = None) -> bool:
    """Ensure the AssignSettingsController.php fork is installed and current.

    Public entry point used by ``InterfaceAssignmentManager.apply()``
    before any REST CRUD call. Fast-paths via checksum comparison so
    repeat applies don't SCP or restart services unnecessarily.

    Args:
        target: Connection details. If ``None``, reads from env via
            ``load_ssh_target``.

    Returns:
        ``True`` if a (re)install actually happened; ``False`` if the
        on-box file was already current.

    Raises:
        RuntimeError: If ``ssh``/``scp`` are missing from ``PATH``,
            credentials cannot be resolved, or any underlying SSH/SCP
            command fails.
    """
    _ensure_ssh_tools_present()
    if target is None:
        target = load_ssh_target()
    return install_controller(target)
