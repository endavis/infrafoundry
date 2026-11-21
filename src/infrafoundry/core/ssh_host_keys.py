"""Pre-generated SSH host keys for blueprint VMs (#1581).

A VM that sets ``ssh_host_key: {address: <addr>}`` gets a host key pair that InfraFoundry
generated ahead of time and keeps in the owning package's SOPS ``secrets.yaml`` under
``variables.ssh_host_keys.<resource-name>``:

```yaml
variables:
  ssh_host_keys:
    vm-01:
      ed25519_private: "-----BEGIN OPENSSH " + "PRIVATE KEY-----..."
      ed25519_public: "ssh-ed25519 AAAA..."
```

cloud-init installs the private key at first boot and the blueprint scripts connect with
``StrictHostKeyChecking=yes`` against a ``known_hosts`` file built from the public keys.
On OCI the key travels the same way, as a ``text/cloud-config`` part of the Tailscale module's
``additional_parts`` (OCI instances with ``tailscale:`` only, #1583).
A VM that is already deployed is *pinned*: only ``ed25519_public`` is recorded, so the VM,
its cloud-init snippet and its Terraform resources do not change.

The helpers here are pure (no I/O). Messages name the resource, the package and the fix,
never a key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import yaml

from infrafoundry.core.package_secret_refs import PACKAGE_REF_PREFIX
from infrafoundry.core.provider import ResourceConfig

#: Reserved key under the package secrets ``variables:`` that holds the host keys.
HOST_KEYS_VARIABLE = "ssh_host_keys"

#: Derived package variable holding the ``;``-separated known_hosts lines.
KNOWN_HOSTS_VARIABLE = "ssh_known_hosts"

#: Resource config field that opts a VM in.
HOST_KEY_FIELD = "ssh_host_key"

_ADDRESS_RE = re.compile(r"^[A-Za-z0-9.:_-]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PUBLIC_KEY_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/]+={0,3}$")
_PRIVATE_KEY_ARMOUR = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"

_FIX_HINT = "run 'foundry secrets host-keys --env <env>'"
FIX_HINT = _FIX_HINT
"""The hint that tells the operator how to pin a VM's host key."""


@dataclass(frozen=True)
class HostKeySpec:
    """The ``ssh_host_key`` block of a resource.

    Attributes:
        address: The address the blueprint scripts connect to.
    """

    address: str


def host_key_config(resource: ResourceConfig) -> HostKeySpec | None:
    """Parse the ``ssh_host_key`` block of a resource.

    Args:
        resource: The resource to read.

    Returns:
        The spec, or None when the resource does not set ``ssh_host_key``.

    Raises:
        ValueError: If the block is not a mapping with a valid ``address``.
    """
    raw = (resource.config or {}).get(HOST_KEY_FIELD)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"'{HOST_KEY_FIELD}' on resource '{resource.name}' must be a mapping")
    address = raw.get("address")
    if not isinstance(address, str) or not address.strip():
        raise ValueError(
            f"'{HOST_KEY_FIELD}.address' on resource '{resource.name}' must be a non-empty string"
        )
    address = address.strip()
    if not _ADDRESS_RE.match(address):
        raise ValueError(
            f"'{HOST_KEY_FIELD}.address' on resource '{resource.name}' may only hold letters, "
            f"digits and . : _ -"
        )
    return HostKeySpec(address=address)


def _entry(resource: ResourceConfig) -> dict[str, Any] | None:
    keys = (resource.package_secrets or {}).get(HOST_KEYS_VARIABLE)
    if not isinstance(keys, dict):
        return None
    entry = keys.get(resource.name)
    return entry if isinstance(entry, dict) else None


def host_key_entry(resource: ResourceConfig) -> tuple[str | None, bool]:
    """Read the resource's host key entry from its package secrets.

    Args:
        resource: The resource to read.

    Returns:
        ``(public key, has a private key)``. The public key is None when it is missing.
        The private key itself is never returned.
    """
    entry = _entry(resource)
    if entry is None:
        return None, False
    public = entry.get("ed25519_public")
    private = entry.get("ed25519_private")
    return (
        public.strip() if isinstance(public, str) and public.strip() else None,
        isinstance(private, str) and bool(private.strip()),
    )


def private_key_ref(name: str) -> str:
    """Return the ``package.`` secret reference of a resource's private host key."""
    return f"{PACKAGE_REF_PREFIX}{HOST_KEYS_VARIABLE}.{name}.ed25519_private"


def apply_host_key(resource: ResourceConfig) -> tuple[str, str] | None:
    """Add the private key reference to ``terraform_secrets`` when a private key exists.

    Idempotent. The resource is changed in place, so pass a copy.

    Args:
        resource: A VM resource.

    Returns:
        ``(terraform variable name, public key)`` when cloud-init has to install a key, or
        None when the resource has no ``ssh_host_key``, is only pinned (no private key), or
        is not from a package.
    """
    # Imported here: provider_mixins imports the config package, which imports this module.
    from infrafoundry.core.provider_mixins import secret_ref_tf_var

    if resource.package_path is None:
        return None
    try:
        spec = host_key_config(resource)
    except ValueError:
        return None
    if spec is None:
        return None
    public, has_private = host_key_entry(resource)
    if not has_private or public is None:
        return None
    ref = private_key_ref(resource.name)
    existing = resource.config.get("terraform_secrets")
    refs = list(existing) if isinstance(existing, list) else []
    if ref not in refs:
        refs.append(ref)
    resource.config["terraform_secrets"] = refs
    return secret_ref_tf_var(ref, resource), public


def cloud_config_fragment(tf_var: str, public: str) -> str:
    """Return the cloud-config lines that install the host key.

    The private key is a Terraform expression, never a value.

    Args:
        tf_var: Terraform variable holding the private key.
        public: The public key line.

    Returns:
        A ``ssh_keys:`` cloud-config fragment.
    """
    return (
        "ssh_keys:\n"
        f"  ed25519_private: ${{jsonencode(var.{tf_var})}}\n"
        f'  ed25519_public: "{public}"\n'
    )


def cloud_config_part(tf_var: str, public: str) -> dict[str, str]:
    """Return a Tailscale module ``additional_parts`` entry that installs the host key.

    Args:
        tf_var: Terraform variable holding the private key.
        public: The public key line.

    Returns:
        A ``text/cloud-config`` part; the private key is only a Terraform expression.
    """
    return {
        "filename": "infrafoundry-ssh-host-key.cfg",
        "content_type": "text/cloud-config",
        "content": "#cloud-config\n" + cloud_config_fragment(tf_var, public),
    }


def known_hosts_value(resources: Iterable[ResourceConfig]) -> str:
    """Build the ``ssh_known_hosts`` package variable.

    Args:
        resources: The package's resources.

    Returns:
        ``;``-separated ``<name>,<address> ssh-ed25519 <key>`` lines (``<name>`` only when
        the address equals the name). Resources without ``ssh_host_key``, or without a valid
        public key, are skipped. Empty string when there are none.
    """
    lines: list[str] = []
    for resource in resources:
        try:
            spec = host_key_config(resource)
        except ValueError:
            continue
        if spec is None:
            continue
        public, _ = host_key_entry(resource)
        if public is None or not _PUBLIC_KEY_RE.match(public):
            continue
        hosts = (
            resource.name if spec.address == resource.name else f"{resource.name},{spec.address}"
        )
        line = f"{hosts} {public}"
        if line not in lines:
            lines.append(line)
    return ";".join(lines)


def known_hosts_for(value: str, name: str) -> tuple[str, ...]:
    """Pick the lines of an ``ssh_known_hosts`` value that name one VM.

    Args:
        value: The ``;``-separated ``ssh_known_hosts`` package variable.
        name: The VM name.

    Returns:
        The lines whose first field, split on commas, contains *name*.
    """
    lines: list[str] = []
    for raw in value.split(";"):
        line = raw.strip()
        fields = line.split(None, 1)
        if fields and name in fields[0].split(","):
            lines.append(line)
    return tuple(lines)


def _describe(resource: ResourceConfig) -> str:
    package = resource.package_name or resource.package_path
    where = f"package '{package}' ({resource.package_path})" if package else "no package"
    return f"resource '{resource.name}' ({where})"


def host_key_problems(
    resource: ResourceConfig,
    cloud_init_data: dict[str, Any] | None = None,
    *,
    require_entry: bool = True,
    allow_tailscale: bool = False,
) -> list[str]:
    """Return what stops a resource's host key from being delivered.

    Args:
        resource: A VM resource.
        cloud_init_data: The merged cloud-init snippet mapping, or None.
        require_entry: Report a missing ``ssh_host_keys.<name>`` entry. Plan-time validation
            sets it; Terraform generation does not, since a missing entry is already an
            ERROR by then and the scripts fail closed on an empty ``ssh_known_hosts``.
        allow_tailscale: Accept a ``tailscale`` block. Only OCI instances deliver the key
            through the Tailscale module's ``additional_parts`` (#1583).

    Returns:
        Messages naming the resource and the fix. Never a key. Empty when the resource has
        no ``ssh_host_key`` or everything is in place.
    """
    try:
        spec = host_key_config(resource)
    except ValueError as exc:
        return [str(exc)]
    if spec is None:
        return []
    if resource.package_path is None:
        return [
            f"Resource '{resource.name}' sets '{HOST_KEY_FIELD}' but does not come from a "
            f"package; host keys are kept in the owning package's secrets.yaml"
        ]
    if not _NAME_RE.match(resource.name):
        return [
            f"{_describe(resource)} sets '{HOST_KEY_FIELD}' but its name may only hold "
            f"letters, digits, '_' and '-' to name a host key"
        ]
    problems: list[str] = []
    if not allow_tailscale and (resource.config or {}).get("tailscale") is not None:
        problems.append(
            f"{_describe(resource)} sets both 'tailscale' and '{HOST_KEY_FIELD}'; pinned host "
            f"keys support 'tailscale' only on OCI instances, not on Proxmox VMs (#1583)"
        )
    if isinstance(cloud_init_data, dict) and "ssh_keys" in cloud_init_data:
        problems.append(
            f"{_describe(resource)} sets '{HOST_KEY_FIELD}' and its cloud-init snippets already "
            f"set 'ssh_keys'; remove 'ssh_keys' from the snippets"
        )
    entry = _entry(resource)
    if entry is None:
        if not require_entry:
            return problems
        problems.append(
            f"{_describe(resource)} sets '{HOST_KEY_FIELD}' but the package's secrets.yaml has "
            f"no '{HOST_KEYS_VARIABLE}.{resource.name}' entry; {_FIX_HINT}"
        )
        return problems
    public, has_private = host_key_entry(resource)
    if public is None:
        problems.append(
            f"{_describe(resource)}: '{HOST_KEYS_VARIABLE}.{resource.name}.ed25519_public' "
            f"is missing; {_FIX_HINT}"
        )
    elif not _PUBLIC_KEY_RE.match(public):
        problems.append(
            f"{_describe(resource)}: '{HOST_KEYS_VARIABLE}.{resource.name}.ed25519_public' "
            f"is not an 'ssh-ed25519 <base64>' line"
        )
    private = entry.get("ed25519_private")
    if has_private and (
        not isinstance(private, str) or not private.strip().startswith(_PRIVATE_KEY_ARMOUR)
    ):
        problems.append(
            f"{_describe(resource)}: '{HOST_KEYS_VARIABLE}.{resource.name}.ed25519_private' "
            f"is not an OpenSSH private key"
        )
    return problems


def _cloud_config_parts_data(parts: Iterable[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Merge the cloud-config ``additional_parts`` so an ``ssh_keys`` clash is visible."""
    merged: dict[str, Any] = {}
    for part in parts or []:
        content = str(part.get("content", ""))
        if part.get("content_type") != "text/cloud-config" and not content.startswith(
            "#cloud-config"
        ):
            continue
        try:
            loaded = yaml.safe_load(content)
        except yaml.YAMLError:
            continue
        if isinstance(loaded, dict):
            merged.update(loaded)
    return merged or None


def oci_host_key_problems(
    resource: ResourceConfig,
    parts: Iterable[dict[str, Any]] | None,
    *,
    require_entry: bool = False,
) -> list[str]:
    """Return what stops an OCI instance's host key from being delivered (#1583).

    Args:
        resource: An OCI ``instance`` resource.
        parts: The instance's Tailscale ``additional_parts``, or None.
        require_entry: Report a missing ``ssh_host_keys.<name>`` entry.

    Returns:
        Messages naming the resource and the fix. Empty when there is no ``ssh_host_key``.
    """
    if (resource.config or {}).get(HOST_KEY_FIELD) is None:
        return []
    problems: list[str] = []
    if (resource.config or {}).get("tailscale") is None:
        problems.append(
            f"{_describe(resource)} sets '{HOST_KEY_FIELD}': ssh_host_key on OCI instances "
            f"needs a 'tailscale' block, which carries the key in its cloud-init parts"
        )
    problems.extend(
        host_key_problems(
            resource,
            _cloud_config_parts_data(parts),
            require_entry=require_entry,
            allow_tailscale=True,
        )
    )
    return problems
