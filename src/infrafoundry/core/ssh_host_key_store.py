"""Generate, pin and store SSH host keys in a package's SOPS ``secrets.yaml`` (#1581).

The subprocess side of ``foundry secrets host-keys``. Every function that runs a program
takes an injected ``run`` (``subprocess.run`` or a stand-in), as
``core/known_hosts.py::forget_on_jumphost`` does. Keys are handed to ``sops`` on stdin, so
no key is ever on a command line or in a plaintext file. Errors are ``SecretError`` and
never carry key material.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess  # nosec B404  # runs ssh-keygen, ssh-keyscan, ssh and sops with list args
import tempfile
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.ssh_host_keys import (
    HOST_KEYS_VARIABLE,
    host_key_entry,
)

Run = Callable[..., "subprocess.CompletedProcess[Any]"]

_TIMEOUT_SECONDS = 60
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PUBLIC_KEY_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/]+={0,3}$")
_SCAN_OPTS = ["-T", "10", "-t", "ed25519"]
_JUMP_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]


class HostKeyAction(StrEnum):
    """What ``foundry secrets host-keys`` does for one VM."""

    SKIP = "skip"
    PIN = "pin"
    GENERATE = "generate"
    REFUSE = "refuse"


@dataclass(frozen=True)
class PlannedAction:
    """The action chosen for one resource.

    Attributes:
        resource: The VM resource.
        action: What to do.
        reason: Why, for ``REFUSE`` and ``SKIP``.
    """

    resource: ResourceConfig
    action: HostKeyAction
    reason: str = ""


def plan_actions(
    resources: Iterable[ResourceConfig],
    deployed: Callable[[ResourceConfig], bool | None],
    regenerate: Collection[str],
) -> list[PlannedAction]:
    """Choose the action for each resource that sets ``ssh_host_key``.

    A resource with a recorded public key is skipped. Without one, a deployed VM is pinned
    (its current key is recorded, so it is not replaced), an undeployed VM gets a generated
    pair, and a VM in between (creating, deleting, in error) is refused. ``regenerate``
    replaces a recorded key, and only for a VM that is not deployed.

    Args:
        resources: Resources that set ``ssh_host_key``.
        deployed: Deployment lookup, see ``jumphost_preflight.deployment_state``.
        regenerate: Resource names whose key is replaced.

    Returns:
        One ``PlannedAction`` per resource, in order.
    """
    planned: list[PlannedAction] = []
    for resource in resources:
        public, _ = host_key_entry(resource)
        state = deployed(resource)
        forced = resource.name in regenerate
        if public is not None and not forced:
            planned.append(PlannedAction(resource, HostKeyAction.SKIP, "key already recorded"))
        elif state is None:
            planned.append(
                PlannedAction(
                    resource,
                    HostKeyAction.REFUSE,
                    "the VM is being created, deleted or is in error; wait for it to settle",
                )
            )
        elif forced and public is not None and state:
            planned.append(
                PlannedAction(
                    resource,
                    HostKeyAction.REFUSE,
                    "the VM is deployed; replacing its key needs a rebuild "
                    "(destroy the VM first, then run this again)",
                )
            )
        elif state:
            planned.append(PlannedAction(resource, HostKeyAction.PIN))
        else:
            planned.append(PlannedAction(resource, HostKeyAction.GENERATE))
    return planned


def _run(
    run: Run, argv: list[str], what: str, stdin: str | None = None, cwd: Path | None = None
) -> str:
    try:
        result = run(
            argv,
            input=stdin,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SecretError(f"{what} timed out after {_TIMEOUT_SECONDS}s") from exc
    except OSError as exc:
        raise SecretError(f"{what} could not run '{argv[0]}': {exc.strerror or exc}") from exc
    if result.returncode != 0:
        # stderr of ssh-keygen, ssh-keyscan and sops holds no key material.
        detail = (result.stderr or "").strip().splitlines()
        raise SecretError(
            f"{what} failed (exit {result.returncode})" + (f": {detail[-1]}" if detail else "")
        )
    return str(result.stdout or "")


def _public_key(line: str) -> str:
    fields = line.split()
    if len(fields) < 2 or not _PUBLIC_KEY_RE.match(f"{fields[0]} {fields[1]}"):
        raise SecretError("the host key is not an ssh-ed25519 public key")
    return f"{fields[0]} {fields[1]}"


def generate_keypair(name: str, run: Run = subprocess.run) -> tuple[str, str]:
    """Generate an ed25519 host key pair with ``ssh-keygen``.

    The pair lives in a 0700 temporary directory that is removed on return.

    Args:
        name: Resource name, used as the key comment.
        run: ``subprocess.run`` or a stand-in.

    Returns:
        ``(private key, public key line without the comment)``.

    Raises:
        SecretError: If ``ssh-keygen`` fails.
    """
    with tempfile.TemporaryDirectory(prefix="infrafoundry-hostkey-") as tmp:
        key = Path(tmp) / "key"
        _run(
            run,
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)],
            f"generating a host key for '{name}'",
        )
        try:
            private = key.read_text(encoding="utf-8")
            public = (Path(tmp) / "key.pub").read_text(encoding="utf-8")
        except OSError as exc:
            raise SecretError(f"ssh-keygen wrote no key pair for '{name}'") from exc
    return private, _public_key(public.strip())


def scan_public_key(address: str, jumphost: str | None, run: Run = subprocess.run) -> str:
    """Fetch the ed25519 host key a VM presents now, with ``ssh-keyscan``.

    Args:
        address: The VM's address.
        jumphost: SSH destination to scan from, or None to scan locally. The hop to the
            jumphost is strict and uses the operator's ``known_hosts``.
        run: ``subprocess.run`` or a stand-in.

    Returns:
        The public key line without the comment.

    Raises:
        SecretError: If the scan fails or does not return exactly one valid key.
    """
    what = f"scanning the host key of '{address}'"
    if jumphost:
        if jumphost.startswith("-"):
            raise SecretError(f"invalid jumphost '{jumphost}'")
        remote = " ".join(["ssh-keyscan", *_SCAN_OPTS, shlex.quote(address)])
        out = _run(run, ["ssh", *_JUMP_OPTS, jumphost, remote], what)
    else:
        out = _run(run, ["ssh-keyscan", *_SCAN_OPTS, address], what)
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(lines) != 1:
        raise SecretError(f"{what} returned {len(lines)} ed25519 keys, expected exactly one")
    fields = lines[0].split()
    if len(fields) != 3:
        raise SecretError(f"{what} returned a malformed line")
    return _public_key(f"{fields[1]} {fields[2]}")


def fingerprint(public: str, run: Run = subprocess.run) -> str:
    """Return the SHA256 fingerprint of a public key line.

    Args:
        public: The public key line.
        run: ``subprocess.run`` or a stand-in.

    Returns:
        E.g. ``SHA256:...``.

    Raises:
        SecretError: If ``ssh-keygen`` fails or prints no fingerprint.
    """
    out = _run(run, ["ssh-keygen", "-lf", "-"], "computing a host key fingerprint", public + "\n")
    fields = out.split()
    if len(fields) < 2:
        raise SecretError("ssh-keygen printed no fingerprint")
    return fields[1]


def ensure_secrets_file(path: Path, cwd: Path, run: Run = subprocess.run) -> bool:
    """Create an encrypted ``secrets.yaml`` with empty ``variables`` when it is missing.

    The file is encrypted with the creation rules that apply to its path (``.sops.yaml``).
    sops finds ``.sops.yaml`` from its working directory, so ``cwd`` is the config repo root.

    Args:
        path: Path of the package's ``secrets.yaml``.
        cwd: Config repo root, used to find ``.sops.yaml``.
        run: ``subprocess.run`` or a stand-in.

    Returns:
        True when the file was created.

    Raises:
        SecretError: If ``sops`` fails.
    """
    if path.exists():
        return False
    argv = [
        "sops",
        "--encrypt",
        "--filename-override",
        str(path),
        "--input-type",
        "yaml",
        "--output-type",
        "yaml",
        "/dev/stdin",
    ]
    encrypted = _run(run, argv, f"creating {path.name}", "variables: {}\n", cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encrypted, encoding="utf-8")
    return True


def write_entry(path: Path, name: str, entry: dict[str, str], run: Run = subprocess.run) -> None:
    """Write ``variables.ssh_host_keys.<name>`` into an encrypted ``secrets.yaml``.

    The value goes to ``sops set --value-stdin`` on stdin.

    Args:
        path: Path of the package's ``secrets.yaml``.
        name: Resource name.
        entry: ``{"ed25519_public": ..., "ed25519_private": ...}``; the private key is
            omitted when pinning.
        run: ``subprocess.run`` or a stand-in.

    Raises:
        SecretError: If the name is not a plain identifier or ``sops`` fails.
    """
    if not _NAME_RE.match(name):
        raise SecretError(f"resource name '{name}' cannot name a host key")
    index = f'["variables"]["{HOST_KEYS_VARIABLE}"]["{name}"]'
    _run(
        run,
        ["sops", "set", "--value-stdin", str(path), index],
        f"writing the host key of '{name}'",
        json.dumps(entry),
    )
