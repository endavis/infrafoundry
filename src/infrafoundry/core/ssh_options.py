"""Shared SSH host-key options and the failure hint for package connections (#1588).

Every package SSH connection to a long-lived host (a jumphost, an ESXi host, a Proxmox
node) checks the host key against the operator's own ``known_hosts``. This module is the
one place that spells the option, so Python call sites import a constant and the Jinja
templates read the ``ssh_host_key_opts`` global that ``TemplateRendererMixin`` registers.

``host_key_hint`` turns the three messages ssh prints for a failed strict check into one
fixed message that says how to record the key.
"""

from __future__ import annotations

import re

STRICT_HOST_KEY_ARGS: tuple[str, ...] = ("-o", "StrictHostKeyChecking=yes")
"""The ssh arguments that check host keys strictly, as an argv fragment."""

STRICT_HOST_KEY_OPTS: str = " ".join(STRICT_HOST_KEY_ARGS)
"""The same option as one string, for templates and ``rsync -e``."""

_CHANGED_RE = re.compile(
    r"Host key for (?P<host>\S+) has changed and you have requested strict checking"
)
_UNKNOWN_RE = re.compile(
    r"No \S+ host key is known for (?P<host>\S+?),? and you have requested strict checking"
)
_FAILED_RE = re.compile(r"Host key verification failed")


def host_key_hint(output: str, host: str | None = None) -> str | None:
    """Explain how to fix a strict host-key failure found in ssh's output.

    Args:
        output: Text ssh (or a tool that wraps it) printed on stderr.
        host: The host the connection was for, used when ssh's message does not name it.

    Returns:
        A message naming the host and the ways to record its key, or ``None`` when
        *output* holds none of ssh's host-key messages.
    """
    changed = _CHANGED_RE.search(output)
    unknown = _UNKNOWN_RE.search(output)
    match = changed or unknown
    if match is None and not _FAILED_RE.search(output):
        return None
    name = match.group("host") if match else (host or "the host")
    name = name.rstrip(",.")
    message = (
        f"The host key for {name} is not in your known_hosts. Record it by connecting "
        f"once with 'ssh {name}' and confirming the fingerprint, or run "
        f"'ssh-keyscan -t ed25519 {name} >> ~/.ssh/known_hosts' after checking the "
        f"fingerprint with 'ssh-keygen -lf'."
    )
    if changed:
        message = (
            f"The host key for {name} has changed. If the change is expected, run "
            f"'ssh-keygen -R {name}' and record the new key: connect once with "
            f"'ssh {name}' and confirm the fingerprint, or run "
            f"'ssh-keyscan -t ed25519 {name} >> ~/.ssh/known_hosts' after checking the "
            f"fingerprint with 'ssh-keygen -lf'."
        )
    return message
