"""Install a certificate and key on a Linux host over SSH.

Content travels on stdin, never on a command line. Each file is written to
``<path>.infrafoundry-new`` under ``umask 077``, given its owner and mode, then one remote
script backs up the old files, moves the new ones in and reloads. If a move or the reload
fails the old files are restored and the reload runs again. SSH is strict about host keys
and never asks.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import subprocess  # nosec B404  # runs ssh with list args
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from infrafoundry.core.certs.install import CertificateTarget, TargetEndpoint
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.ssh_options import STRICT_HOST_KEY_ARGS, host_key_hint

Run = Callable[..., "subprocess.CompletedProcess[Any]"]

NEW_SUFFIX = ".infrafoundry-new"
BACKUP_SUFFIX = ".infrafoundry-bak"
NONE_SUFFIX = ".infrafoundry-none"
RELOAD_FAILED = 12
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL)
_TIMEOUT_SECONDS = 90
_MARKER = "infrafoundry-reload-failed"


class SshCertificateInstaller:
    """Installs certificate files on a host over SSH."""

    def __init__(self, run: Run = subprocess.run) -> None:
        """Initialize the installer.

        Args:
            run: ``subprocess.run`` or a stand-in.
        """
        self._run = run

    def install(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        """Write the files, move them into place and reload.

        Args:
            target: A resolved target (with an endpoint).
            cert_pem: The leaf certificate.
            chain_pem: The intermediate chain (may be empty).
            key_pem: The private key.

        Raises:
            CertificateInstallError: If a step fails. The old files are back in place when the
                move or the reload failed. The message never carries key material.
        """
        endpoint = target.endpoint
        if endpoint is None:
            raise CertificateInstallError(f"target '{target.resource}' has no SSH endpoint")
        files = _files(target, cert_pem, chain_pem, key_pem)
        with _known_hosts_file(endpoint) as known_hosts:
            try:
                for path, content, _mode in files:
                    self._ssh(
                        endpoint,
                        target,
                        f"umask 077; cat > {shlex.quote(path + NEW_SUFFIX)}",
                        content,
                        f"writing {path}",
                        key_pem,
                        known_hosts,
                    )
                self._ssh(
                    endpoint,
                    target,
                    _finalize_script(target, files),
                    None,
                    "installing",
                    key_pem,
                    known_hosts,
                )
            except CertificateInstallError:
                self._remove_new(endpoint, target, [p for p, _, _ in files], key_pem, known_hosts)
                raise

    def _remove_new(
        self,
        endpoint: TargetEndpoint,
        target: CertificateTarget,
        paths: list[str],
        key_pem: str,
        known_hosts: Path | None,
    ) -> None:
        script = "rm -f " + " ".join(shlex.quote(p + NEW_SUFFIX) for p in paths)
        # The original error is the one to report.
        with contextlib.suppress(CertificateInstallError):
            self._ssh(endpoint, target, script, None, "cleaning up", key_pem, known_hosts)

    def _ssh(
        self,
        endpoint: TargetEndpoint,
        target: CertificateTarget,
        script: str,
        stdin: str | None,
        what: str,
        key_pem: str,
        known_hosts: Path | None,
    ) -> None:
        remote = f"{'sudo -n ' if target.sudo else ''}sh -c {shlex.quote(script)}"
        argv = _argv(endpoint, remote, known_hosts)
        try:
            result = self._run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise CertificateInstallError(
                f"{what} on '{target.resource}' timed out after {_TIMEOUT_SECONDS}s"
            ) from None
        except OSError as exc:
            raise CertificateInstallError(
                f"{what} on '{target.resource}': could not run ssh: {exc.strerror or exc}"
            ) from None
        if result.returncode == 0:
            return
        stderr = str(result.stderr or "")
        if result.returncode == RELOAD_FAILED or _MARKER in stderr:
            raise CertificateInstallError(
                f"the reload on '{target.resource}' failed; the previous certificate was restored"
            )
        alias = endpoint.host_key_alias
        if alias and alias in stderr and host_key_hint(stderr, alias):
            hint: str | None = _pinned_key_hint(alias)
        else:
            hint = host_key_hint(stderr, endpoint.jumphost or endpoint.address)
        lines = _scrub(stderr, key_pem).strip().splitlines()
        detail = hint or (lines[-1] if lines else "")
        raise CertificateInstallError(
            f"{what} on '{target.resource}' failed (exit {result.returncode})"
            + (f": {detail}" if detail else "")
        )


@contextlib.contextmanager
def _known_hosts_file(endpoint: TargetEndpoint) -> Iterator[Path | None]:
    """Yield a 0600 file of the pinned lines for a direct target, else ``None``; removed after."""
    if not endpoint.known_hosts or endpoint.jumphost:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="infrafoundry-kh-") as directory:
        path = Path(directory) / "known_hosts"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(endpoint.known_hosts) + "\n")
        yield path


def _argv(endpoint: TargetEndpoint, remote: str, known_hosts: Path | None) -> list[str]:
    """Build the ssh argv; unchanged from the plain host form without a pin or jumphost."""
    base = ["ssh", "-o", "BatchMode=yes", *STRICT_HOST_KEY_ARGS, "-o", "ConnectTimeout=10"]
    if endpoint.jumphost:
        return [*base, endpoint.jumphost, _jump_remote(endpoint, remote)]
    argv = [*base, "-p", str(endpoint.port)]
    if known_hosts is not None:
        argv += ["-o", f"UserKnownHostsFile={known_hosts}", "-o", "GlobalKnownHostsFile=/dev/null"]
    if endpoint.host_key_alias:
        argv += ["-o", f"HostKeyAlias={endpoint.host_key_alias}"]
    if endpoint.key_file:
        argv += ["-i", endpoint.key_file, "-o", "IdentitiesOnly=yes"]
    destination = f"{endpoint.user}@{endpoint.address}" if endpoint.user else endpoint.address
    return [*argv, destination, remote]


def _jump_remote(endpoint: TargetEndpoint, remote: str) -> str:
    """The script run on the jump host: stage the pinned keys, then ssh strictly to the VM."""
    q = shlex.quote
    lines = " ".join(q(line) for line in endpoint.known_hosts)
    destination = f"{endpoint.user}@{endpoint.address}" if endpoint.user else endpoint.address
    alias = q(endpoint.host_key_alias or endpoint.address)
    return (
        "kh=$(mktemp) && trap 'rm -f \"$kh\"' EXIT && "
        f"printf '%s\\n' {lines} >\"$kh\" && "
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "
        '-o UserKnownHostsFile="$kh" -o GlobalKnownHostsFile=/dev/null '
        f"-o HostKeyAlias={alias} -o ConnectTimeout=10 -p {endpoint.port} "
        f"{q(destination)} {q(remote)}"
    )


def _pinned_key_hint(name: str) -> str:
    return (
        f"The host key presented by '{name}' does not match the key pinned in its package's "
        f"secrets.yaml, so the connection was refused. Run 'foundry secrets host-keys "
        f"--env <env>' (add '--regenerate {name}' after a rebuild)."
    )


def _scrub(text: str, key_pem: str) -> str:
    """Remove PEM blocks and every line of the key from ssh's output."""
    text = _PEM_RE.sub("", text)
    secret_lines = {ln.strip() for ln in key_pem.splitlines() if ln.strip()}
    return "\n".join(
        ln for ln in text.splitlines() if ln.strip() not in secret_lines and "PRIVATE" not in ln
    )


def _files(
    target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
) -> list[tuple[str, str, str]]:
    """Return ``(path, content, mode)`` for each file to install."""
    files: list[tuple[str, str, str]] = []
    if target.cert_path:
        files.append((target.cert_path, cert_pem, target.cert_mode))
    if target.fullchain_path:
        files.append((target.fullchain_path, cert_pem + chain_pem, target.cert_mode))
    files.append((target.key_path, key_pem, target.key_mode))
    return files


def _finalize_script(target: CertificateTarget, files: list[tuple[str, str, str]]) -> str:
    """Build the one remote script that backs up, swaps, reloads and rolls back."""
    q = shlex.quote
    owner = q(f"{target.owner}:{target.group}")
    new = [q(p + NEW_SUFFIX) for p, _, _ in files]
    leftovers = " ".join(f"{q(p + BACKUP_SUFFIX)} {q(p + NONE_SUFFIX)}" for p, _, _ in files)
    restore = "; ".join(
        f"if [ -e {q(p + NONE_SUFFIX)} ]; then rm -f {q(p)}; "
        f"elif [ -e {q(p + BACKUP_SUFFIX)} ]; then mv -f {q(p + BACKUP_SUFFIX)} {q(p)}; fi"
        for p, _, _ in files
    )
    reload_cmd = " ".join(q(a) for a in target.reload)
    lines = [
        "set -u",
        f"trap 'rm -f {' '.join(new)} {leftovers}' EXIT",
        f"rollback() {{ {restore}; }}",
    ]
    for (path, _, mode), tmp in zip(files, new, strict=True):
        lines.append(f"chown {owner} {tmp} && chmod {q(mode)} {tmp} || exit 11")
        lines.append(
            f"if [ -e {q(path)} ]; then cp -p {q(path)} {q(path + BACKUP_SUFFIX)} || exit 13; "
            f"else : > {q(path + NONE_SUFFIX)}; fi"
        )
    for (path, _, _), tmp in zip(files, new, strict=True):
        lines.append(f"mv -f {tmp} {q(path)} || {{ rollback; rm -f {leftovers}; exit 14; }}")
    if target.reload:
        lines.append(f"if ! {reload_cmd}; then")
        lines.append("  rollback")
        lines.append(f"  {reload_cmd} || true")
        lines.append(f"  rm -f {leftovers}")
        lines.append(f"  echo {_MARKER} >&2; exit {RELOAD_FAILED}")
        lines.append("fi")
    lines.append(f"rm -f {leftovers}")
    return "\n".join(lines)
