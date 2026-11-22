"""Schema checks for ``host`` resources, shared by the provider and the validator."""

from __future__ import annotations

import copy
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import TailscaleSchemaError, process_tailscale_config
from infrafoundry.core.validation import ValidationLevel

KNOWN_KEYS = frozenset(
    {
        "name",
        "address",
        "ssh_user",
        "ssh_port",
        "ssh_private_key_file",
        "groups",
        "ansible",
        "tailscale",
        "terraform_secrets",
    }
)
"""Keys a ``host`` resource may carry; any other key is reported as a warning."""

DEFAULT_SSH_PORT = 22

_GROUP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME_RE = re.compile(rf"^{_LABEL}(?:\.{_LABEL})*$")
_USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class HostFinding:
    """One schema finding for a host resource."""

    resource: str
    level: ValidationLevel
    message: str


def is_valid_address(address: object) -> bool:
    """Return True for an IPv4/IPv6 address or a DNS hostname that cannot be read as an option.

    Args:
        address: The configured ``address`` value.
    """
    if not isinstance(address, str) or not address or address.startswith("-"):
        return False
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return bool(_HOSTNAME_RE.fullmatch(address)) and len(address) <= 253
    return True


def tailscale_auth_ref(resource: ResourceConfig) -> str | None:
    """Return the secret reference holding a host's Tailscale auth secret.

    Args:
        resource: A host resource whose ``tailscale:`` block already validated.

    Returns:
        The dotted secret path or ``secret://`` URI (the auth key, or the OAuth client secret), or
        ``None`` when the host has no ``tailscale:`` block.
    """
    block = (resource.config or {}).get("tailscale")
    if not isinstance(block, dict):
        return None
    auth = block.get("auth")
    if not isinstance(auth, dict):
        return None
    if "auth_key_secret" in auth:
        return str(auth["auth_key_secret"])
    oauth = auth.get("oauth")
    if isinstance(oauth, dict) and oauth.get("client_secret_secret"):
        return str(oauth["client_secret_secret"])
    return None


def _check_playbooks(name: str, ansible: Any, repo_root: Path | None) -> list[HostFinding]:
    """Check the ``ansible:`` block of one host."""
    err = ValidationLevel.ERROR
    if not isinstance(ansible, dict):
        return [HostFinding(name, err, f"Host '{name}' ansible must be a mapping")]
    findings: list[HostFinding] = []
    for key in ansible:
        if key != "playbooks":
            findings.append(
                HostFinding(
                    name, ValidationLevel.WARNING, f"Host '{name}' ansible.{key} is unknown"
                )
            )
    playbooks = ansible.get("playbooks", [])
    if not isinstance(playbooks, list) or not all(isinstance(p, str) and p for p in playbooks):
        return [
            *findings,
            HostFinding(name, err, f"Host '{name}' ansible.playbooks must be a list of paths"),
        ]
    for playbook in playbooks:
        path = Path(playbook)
        if path.is_absolute() or ".." in path.parts:
            findings.append(
                HostFinding(
                    name,
                    err,
                    f"Host '{name}' playbook '{playbook}' must be a relative path inside "
                    "the config repo",
                )
            )
            continue
        if repo_root is None:
            continue
        resolved = (repo_root / path).resolve()
        if not resolved.is_relative_to(repo_root.resolve()):
            findings.append(
                HostFinding(
                    name,
                    err,
                    f"Host '{name}' playbook '{playbook}' resolves outside the config repo",
                )
            )
        elif not resolved.is_file():
            findings.append(
                HostFinding(name, err, f"Host '{name}' playbook '{playbook}' does not exist")
            )
    return findings


def _check_tailscale(resource: ResourceConfig) -> list[HostFinding]:
    """Check the ``tailscale:`` block of one host (validated on a copy)."""
    block = (resource.config or {}).get("tailscale")
    if block is None:
        return []
    err = ValidationLevel.ERROR
    try:
        module = process_tailscale_config(copy.deepcopy(resource), base64_encode=False)
    except TailscaleSchemaError as exc:
        return [HostFinding(resource.name, err, str(exc))]
    if module and module.get("additional_parts"):
        return [
            HostFinding(
                resource.name,
                err,
                f"Host '{resource.name}' tailscale.additional_parts is cloud-init only and "
                "is not supported on an existing host",
            )
        ]
    if module and module.get("advertise_exit_node"):
        return [
            HostFinding(
                resource.name,
                err,
                f"Host '{resource.name}' tailscale.advertise_exit_node is only supported on "
                "cloud-init instances, not on an existing host",
            )
        ]
    return []


def check_host(resource: ResourceConfig, repo_root: Path | None) -> list[HostFinding]:
    """Return the schema findings of one host resource.

    Args:
        resource: A ``host`` resource.
        repo_root: The config repo root playbook paths are relative to; ``None``
            skips the existence check.
    """
    name = resource.name
    config = resource.config or {}
    err = ValidationLevel.ERROR
    findings: list[HostFinding] = []

    if "address" not in config:
        findings.append(HostFinding(name, err, f"Host '{name}' requires 'address'"))
    elif not is_valid_address(config["address"]):
        findings.append(
            HostFinding(
                name,
                err,
                f"Host '{name}' address {config['address']!r} is not an IP address or hostname "
                "(it must not start with '-')",
            )
        )

    user = config.get("ssh_user")
    if user is not None and (not isinstance(user, str) or not _USER_RE.fullmatch(user)):
        findings.append(HostFinding(name, err, f"Host '{name}' ssh_user is not a valid user name"))

    port = config.get("ssh_port", DEFAULT_SSH_PORT)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        findings.append(HostFinding(name, err, f"Host '{name}' ssh_port must be 1-65535"))

    key_file = config.get("ssh_private_key_file")
    if key_file is not None and (not isinstance(key_file, str) or not key_file):
        findings.append(
            HostFinding(name, err, f"Host '{name}' ssh_private_key_file must be a path string")
        )

    groups = config.get("groups", [])
    if not isinstance(groups, list) or not all(
        isinstance(g, str) and _GROUP_RE.fullmatch(g) for g in groups
    ):
        findings.append(
            HostFinding(
                name,
                err,
                f"Host '{name}' groups must be a list of names matching [A-Za-z_][A-Za-z0-9_]*",
            )
        )

    if "ansible" in config:
        findings.extend(_check_playbooks(name, config["ansible"], repo_root))
    findings.extend(_check_tailscale(resource))

    for key in sorted(set(config) - KNOWN_KEYS):
        findings.append(
            HostFinding(name, ValidationLevel.WARNING, f"Host '{name}' has unknown key '{key}'")
        )
    return findings


def check_hosts(resources: list[ResourceConfig], repo_root: Path | None) -> list[HostFinding]:
    """Return the schema findings of every ``host`` resource in the list.

    Args:
        resources: Resources to check; other types are ignored.
        repo_root: The config repo root, or ``None`` to skip playbook existence checks.
    """
    findings: list[HostFinding] = []
    for resource in resources:
        if resource.type == "host":
            findings.extend(check_host(resource, repo_root))
    return findings
