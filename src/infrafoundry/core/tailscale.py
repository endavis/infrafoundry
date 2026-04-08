"""Shared helpers for the Tailscale cloud-init Terraform module integration.

Phase 2 of issue #212. Consumed by both the OCI and Proxmox providers to:

1. Validate the optional ``tailscale:`` resource config block.
2. Normalize it into a ``tailscale_module_config`` dict that the provider
   template can render as a ``module "tailscale_<name>"`` block.
3. Auto-populate the resource's ``terraform_secrets:`` list with the
   referenced secret paths so the Phase 1 secrets→TF_VAR_* bridge picks
   them up without the user duplicating the refs.

The Tailscale module itself lives at:

    https://github.com/tailscale/terraform-cloudinit-tailscale

and is pinned to ``0.0.11`` (pre-1.0; latest as of phase 2 implementation).

Exactly one of these auth modes must be set on every ``tailscale:`` block:

- ``auth.auth_key_secret: "<dotted.secret.path>"`` — static auth key.
- ``auth.oauth.client_id_secret: ...`` + ``auth.oauth.client_secret_secret: ...``
  — OAuth client (ephemeral keys).

Both point into the env's decrypted ``secrets:`` dict via dotted paths, the
same way Phase 1 declares ``terraform_secrets:`` entries.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import sanitize_secret_ref_to_tf_var

#: Pinned version of the ``tailscale/cloudinit/tailscale`` module.
TAILSCALE_MODULE_VERSION = "0.0.11"
TAILSCALE_MODULE_SOURCE = "tailscale/cloudinit/tailscale"


class TailscaleSchemaError(ValueError):
    """Raised when a ``tailscale:`` resource config block is malformed."""


def _sanitize_module_name(resource_name: str) -> str:
    """Convert a resource name into a Terraform-safe module name suffix."""
    return resource_name.replace("-", "_").replace(".", "_")


def _validate_auth_block(resource_name: str, auth: Any) -> dict[str, Any]:
    """Validate the ``tailscale.auth`` sub-block.

    Returns a dict describing the resolved auth mode with keys:

    - ``mode``: ``"auth_key"`` or ``"oauth"``
    - ``secret_refs``: list of dotted secret paths that must be resolvable
    - for ``auth_key``: ``auth_key_ref``
    - for ``oauth``: ``client_id_ref`` and ``client_secret_ref``
    """
    if not isinstance(auth, dict):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.auth must be a mapping, "
            f"got {type(auth).__name__}."
        )

    has_auth_key = "auth_key_secret" in auth
    has_oauth = "oauth" in auth

    if has_auth_key and has_oauth:
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.auth has both "
            f"'auth_key_secret' and 'oauth'; exactly one is required."
        )
    if not has_auth_key and not has_oauth:
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.auth must set exactly one "
            f"of 'auth_key_secret' or 'oauth'."
        )

    if has_auth_key:
        ref = auth["auth_key_secret"]
        if not isinstance(ref, str) or not ref:
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.auth.auth_key_secret "
                f"must be a non-empty dotted secret reference string."
            )
        return {
            "mode": "auth_key",
            "auth_key_ref": ref,
            "secret_refs": [ref],
        }

    oauth = auth["oauth"]
    if not isinstance(oauth, dict):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.auth.oauth must be a "
            f"mapping, got {type(oauth).__name__}."
        )
    client_id = oauth.get("client_id_secret")
    client_secret = oauth.get("client_secret_secret")
    for field_name, value in (
        ("client_id_secret", client_id),
        ("client_secret_secret", client_secret),
    ):
        if not isinstance(value, str) or not value:
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.auth.oauth."
                f"{field_name} must be a non-empty dotted secret reference "
                f"string."
            )
    return {
        "mode": "oauth",
        "client_id_ref": client_id,
        "client_secret_ref": client_secret,
        "secret_refs": [client_id, client_secret],
    }


def _validate_tags(resource_name: str, tags: Any) -> list[str]:
    """Validate the ``advertise_tags`` list."""
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.advertise_tags must be a "
            f"list, got {type(tags).__name__}."
        )
    for tag in tags:
        if not isinstance(tag, str):
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.advertise_tags entry "
                f"{tag!r} is not a string."
            )
        if not tag.startswith("tag:"):
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.advertise_tags entry "
                f"{tag!r} must start with 'tag:'."
            )
    return list(tags)


def _validate_routes(resource_name: str, routes: Any) -> list[str]:
    """Validate the ``advertise_routes`` list."""
    if routes is None:
        return []
    if not isinstance(routes, list):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.advertise_routes must be "
            f"a list, got {type(routes).__name__}."
        )
    for route in routes:
        if not isinstance(route, str):
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.advertise_routes "
                f"entry {route!r} is not a string."
            )
    return list(routes)


def _validate_additional_parts(resource_name: str, parts: Any) -> list[dict[str, Any]]:
    """Validate the ``additional_parts`` escape-hatch list."""
    if parts is None:
        return []
    if not isinstance(parts, list):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.additional_parts must be "
            f"a list, got {type(parts).__name__}."
        )
    validated: list[dict[str, Any]] = []
    for idx, part in enumerate(parts):
        if not isinstance(part, dict):
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.additional_parts[{idx}]"
                f" must be a mapping, got {type(part).__name__}."
            )
        content = part.get("content")
        if not isinstance(content, str):
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.additional_parts[{idx}]"
                f".content must be a string."
            )
        entry: dict[str, Any] = {"content": content}
        for optional_field in ("filename", "content_type", "merge_type"):
            if optional_field in part:
                val = part[optional_field]
                if not isinstance(val, str):
                    raise TailscaleSchemaError(
                        f"Resource '{resource_name}' tailscale."
                        f"additional_parts[{idx}].{optional_field} must be "
                        f"a string."
                    )
                entry[optional_field] = val
        validated.append(entry)
    return validated


def _validate_bool(resource_name: str, field: str, value: Any, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.{field} must be a bool, "
            f"got {type(value).__name__}."
        )
    return value


def process_tailscale_config(
    resource: ResourceConfig,
    *,
    base64_encode: bool,
) -> dict[str, Any] | None:
    """Validate and normalize a resource's ``tailscale:`` config block.

    If the resource has no ``tailscale:`` block, returns ``None`` and leaves
    the resource untouched.

    Otherwise:

    1. Validates the schema (raises :class:`TailscaleSchemaError` on bad
       input).
    2. Rejects the resource if ``cloud_init_snippets`` is also set (mutual
       exclusion — the Phase 2 plan calls these two paths exclusive).
    3. Mutates ``resource.config["terraform_secrets"]`` to include every
       secret reference from the tailscale ``auth:`` block (deduped,
       order-preserving), so the Phase 1 secrets→TF_VAR_* bridge picks
       them up.
    4. Returns a ``tailscale_module_config`` dict ready for direct
       consumption by a provider template.

    Args:
        resource: The resource to inspect/mutate. The ``tailscale:`` block
            is read from ``resource.config["tailscale"]`` if present.
        base64_encode: Value to pass to the Tailscale module's
            ``base64_encode`` input. OCI wants ``True`` (user_data takes
            base64); Proxmox wants ``False`` (the cloud-init file is
            stored raw on Proxmox storage).

    Returns:
        A ``tailscale_module_config`` dict, or ``None`` if no tailscale
        block is configured on this resource.

    Raises:
        TailscaleSchemaError: If the schema is invalid, or if
            ``cloud_init_snippets`` and ``tailscale`` are both set.
    """
    config = resource.config or {}
    tailscale = config.get("tailscale")
    if tailscale is None:
        return None

    if not isinstance(tailscale, dict):
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' tailscale: must be a mapping, "
            f"got {type(tailscale).__name__}."
        )

    if config.get("cloud_init_snippets"):
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' has both 'cloud_init_snippets' and "
            f"'tailscale' set. These are mutually exclusive; move any extra "
            f"cloud-init pieces into 'tailscale.additional_parts'."
        )

    if "auth" not in tailscale:
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' tailscale: requires an 'auth' "
            f"sub-block (with either 'auth_key_secret' or 'oauth')."
        )

    auth_info = _validate_auth_block(resource.name, tailscale["auth"])

    hostname = tailscale.get("hostname")
    if hostname is None:
        hostname = resource.name
    elif not isinstance(hostname, str) or not hostname:
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' tailscale.hostname must be a non-empty string if set."
        )

    track = tailscale.get("track", "stable")
    if not isinstance(track, str) or not track:
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' tailscale.track must be a non-empty string."
        )

    enable_ssh = _validate_bool(resource.name, "enable_ssh", tailscale.get("enable_ssh"), False)
    accept_dns = _validate_bool(resource.name, "accept_dns", tailscale.get("accept_dns"), True)
    accept_routes = _validate_bool(
        resource.name, "accept_routes", tailscale.get("accept_routes"), False
    )

    advertise_tags = _validate_tags(resource.name, tailscale.get("advertise_tags"))
    advertise_routes = _validate_routes(resource.name, tailscale.get("advertise_routes"))
    additional_parts = _validate_additional_parts(resource.name, tailscale.get("additional_parts"))

    # Build the module config the template consumes.
    module_name = f"tailscale_{_sanitize_module_name(resource.name)}"
    module_config: dict[str, Any] = {
        "module_name": module_name,
        "hostname": hostname,
        "enable_ssh": enable_ssh,
        "accept_dns": accept_dns,
        "accept_routes": accept_routes,
        "advertise_tags": advertise_tags,
        "advertise_routes": advertise_routes,
        "track": track,
        "additional_parts": additional_parts,
        "base64_encode": base64_encode,
        "source": TAILSCALE_MODULE_SOURCE,
        "version": TAILSCALE_MODULE_VERSION,
        "auth_mode": auth_info["mode"],
    }

    if auth_info["mode"] == "auth_key":
        module_config["auth_key_var"] = sanitize_secret_ref_to_tf_var(auth_info["auth_key_ref"])
    else:
        module_config["oauth_client_id_var"] = sanitize_secret_ref_to_tf_var(
            auth_info["client_id_ref"]
        )
        module_config["oauth_client_secret_var"] = sanitize_secret_ref_to_tf_var(
            auth_info["client_secret_ref"]
        )

    # Auto-populate terraform_secrets so Phase 1's bridge declares the
    # sensitive variables and injects values at apply time. Dedup while
    # preserving the user's original ordering.
    existing = config.get("terraform_secrets") or []
    if not isinstance(existing, list):
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' has a non-list terraform_secrets "
            f"value: {type(existing).__name__}."
        )
    merged: list[str] = list(existing)
    for ref in auth_info["secret_refs"]:
        if ref not in merged:
            merged.append(ref)
    config["terraform_secrets"] = merged

    return module_config


def instances_require_cloudinit_provider(
    resources: list[ResourceConfig],
) -> bool:
    """Return True if any resource in the list declares a ``tailscale:`` block.

    Used by provider.tf.j2 templates to decide whether to emit the
    ``hashicorp/cloudinit`` ``required_providers`` entry (the Tailscale
    module depends on it).
    """
    return any((r.config or {}).get("tailscale") is not None for r in resources)
