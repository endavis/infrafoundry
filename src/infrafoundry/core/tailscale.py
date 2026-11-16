"""Shared helpers for the Tailscale cloud-init Terraform module integration.

Phase 2 of issue #212. Consumed by the AWS, OCI and Proxmox providers to:

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
- ``auth.oauth.client_secret_secret: ...`` — OAuth client secret. The module
  has no OAuth mode of its own (``client_id`` / ``client_secret`` are only
  valid with ``id_token`` or ``audience``), so the OAuth client secret is
  passed as the module's ``auth_key``. Tailscale requires ``advertise_tags``
  for OAuth-generated keys. ``oauth.client_id_secret`` is optional and unused.

After ``foundry infra destroy`` deletes an instance, :func:`plan_tailnet_cleanup`
and :func:`remove_tailnet_devices` remove its tailnet device through the
Tailscale API (OAuth mode only; see issue #1401).

Both point into the env's decrypted ``secrets:`` dict via dotted paths, the
same way Phase 1 declares ``terraform_secrets:`` entries.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import requests

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import sanitize_secret_ref_to_tf_var

logger = logging.getLogger(__name__)

#: Base URL of the Tailscale HTTP API.
TAILSCALE_API_BASE = "https://api.tailscale.com/api/v2"

#: Pinned version of the ``tailscale/tailscale/cloudinit`` module.
TAILSCALE_MODULE_VERSION = "0.0.11"
TAILSCALE_MODULE_SOURCE = "tailscale/tailscale/cloudinit"


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
    - for ``oauth``: ``client_secret_ref`` and ``client_id_ref`` (``None``
      when ``client_id_secret`` is absent; it is optional for the module but
      needed for tailnet cleanup, and must be a non-empty string when present)
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
    client_secret = oauth.get("client_secret_secret")
    if "client_id_secret" in oauth:
        client_id = oauth["client_id_secret"]
        if not isinstance(client_id, str) or not client_id:
            raise TailscaleSchemaError(
                f"Resource '{resource_name}' tailscale.auth.oauth."
                f"client_id_secret must be a non-empty dotted secret "
                f"reference string."
            )
    if not isinstance(client_secret, str) or not client_secret:
        raise TailscaleSchemaError(
            f"Resource '{resource_name}' tailscale.auth.oauth."
            f"client_secret_secret must be a non-empty dotted secret "
            f"reference string."
        )
    return {
        "mode": "oauth",
        "client_id_ref": oauth.get("client_id_secret"),
        "client_secret_ref": client_secret,
        "secret_refs": [client_secret],
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

    remove_on_destroy = _validate_bool(
        resource.name, "remove_on_destroy", tailscale.get("remove_on_destroy"), True
    )

    advertise_tags = _validate_tags(resource.name, tailscale.get("advertise_tags"))
    if auth_info["mode"] == "oauth" and not advertise_tags:
        raise TailscaleSchemaError(
            f"Resource '{resource.name}' tailscale.advertise_tags must be a "
            f"non-empty list when auth.oauth is used (Tailscale requires tags "
            f"for OAuth-generated auth keys)."
        )
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
        "remove_on_destroy": remove_on_destroy,
        "advertise_tags": advertise_tags,
        "advertise_routes": advertise_routes,
        "track": track,
        "additional_parts": additional_parts,
        "base64_encode": base64_encode,
        "source": TAILSCALE_MODULE_SOURCE,
        "version": TAILSCALE_MODULE_VERSION,
        "auth_mode": auth_info["mode"],
    }

    # OAuth mode passes the client secret as the module's ``auth_key``.
    auth_ref = auth_info["auth_key_ref" if auth_info["mode"] == "auth_key" else "client_secret_ref"]
    module_config["auth_key_var"] = sanitize_secret_ref_to_tf_var(auth_ref)

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


@dataclass(frozen=True)
class TailnetDeviceCleanup:
    """One tailnet device to remove after its instance was destroyed."""

    resource_name: str
    hostname: str
    tags: tuple[str, ...]
    client_id_ref: str
    client_secret_ref: str


@dataclass
class TailnetCleanupReport:
    """Outcome of :func:`remove_tailnet_devices` as human-readable messages."""

    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def plan_tailnet_cleanup(
    resources: list[ResourceConfig],
) -> tuple[list[TailnetDeviceCleanup], list[str]]:
    """Work out which destroyed resources need their tailnet device removed.

    Resources without a ``tailscale:`` block are ignored. The input resources
    are not mutated.

    Args:
        resources: Resources whose destroy outcome was a delete.

    Returns:
        A tuple of cleanup targets and skip/warning messages explaining every
        resource with a ``tailscale:`` block that is not a target.
    """
    targets: list[TailnetDeviceCleanup] = []
    messages: list[str] = []
    for resource in resources:
        raw = (resource.config or {}).get("tailscale")
        if raw is None:
            continue
        try:
            module_config = process_tailscale_config(copy.deepcopy(resource), base64_encode=False)
            if module_config is None or not isinstance(raw, dict):
                continue
            auth_info = _validate_auth_block(resource.name, raw["auth"])
        except TailscaleSchemaError as exc:
            messages.append(f"Tailnet cleanup skipped for '{resource.name}': {exc}")
            continue
        if not module_config["remove_on_destroy"]:
            messages.append(
                f"Tailnet cleanup skipped for '{resource.name}': remove_on_destroy is false."
            )
            continue
        if auth_info["mode"] != "oauth":
            messages.append(
                f"Tailnet cleanup skipped for '{resource.name}': an auth key cannot call "
                f"the Tailscale API; remove the device by hand."
            )
            continue
        if not auth_info["client_id_ref"]:
            messages.append(
                f"Tailnet cleanup skipped for '{resource.name}': "
                f"auth.oauth.client_id_secret is required to call the Tailscale API."
            )
            continue
        targets.append(
            TailnetDeviceCleanup(
                resource_name=resource.name,
                hostname=module_config["hostname"],
                tags=tuple(module_config["advertise_tags"]),
                client_id_ref=auth_info["client_id_ref"],
                client_secret_ref=auth_info["client_secret_ref"],
            )
        )
    return targets, messages


def device_matches(device: dict[str, Any], hostname: str, tags: Iterable[str]) -> bool:
    """Return True if a tailnet device has this hostname and shares a tag.

    Both comparisons are case-insensitive. A device with no tags never matches.
    """
    device_host = device.get("hostname")
    if not isinstance(device_host, str) or device_host.casefold() != hostname.casefold():
        return False
    device_tags = device.get("tags")
    if not isinstance(device_tags, list):
        return False
    wanted = {t.casefold() for t in tags}
    return any(isinstance(t, str) and t.casefold() in wanted for t in device_tags)


def _fetch_devices(
    http: requests.Session, api_base: str, token_creds: tuple[str, str], timeout: float
) -> tuple[str, list[dict[str, Any]]]:
    """Get an OAuth token and the tailnet device list.

    Returns:
        The access token and the devices.

    Raises:
        RuntimeError: On a non-2xx response; the message carries the status only.
        requests.RequestException: On a network error.
        ValueError: On an unparsable body.
        KeyError: On a missing field.
        TypeError: On an unexpected shape.
    """
    client_id, client_secret = token_creds
    resp = http.post(
        f"{api_base}/oauth/token",
        data={"client_id": client_id, "client_secret": client_secret},
        timeout=timeout,
    )
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"token request failed with HTTP {resp.status_code}")
    token = resp.json()["access_token"]
    if not isinstance(token, str):
        raise TypeError("access_token is not a string")
    resp = http.get(
        f"{api_base}/tailnet/-/devices",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"device list request failed with HTTP {resp.status_code}")
    devices = resp.json()["devices"]
    if not isinstance(devices, list):
        raise TypeError("devices is not a list")
    return token, [d for d in devices if isinstance(d, dict)]


def remove_tailnet_devices(
    cleanups: list[TailnetDeviceCleanup],
    secrets: dict[str, Any] | None,
    *,
    session: requests.Session | None = None,
    api_base: str = TAILSCALE_API_BASE,
    timeout: float = 30.0,
) -> TailnetCleanupReport:
    """Delete the tailnet devices of destroyed instances through the Tailscale API.

    Never raises on network or parse errors; they become warnings. Messages
    carry only status codes, secret ref paths, hostnames and device ids, never
    credentials or response bodies.

    Args:
        cleanups: Targets from :func:`plan_tailnet_cleanup`.
        secrets: The environment's decrypted ``secrets`` mapping.
        session: HTTP session, injectable for tests.
        api_base: Tailscale API base URL.
        timeout: Per-request timeout in seconds.

    Returns:
        A report of removed, skipped and warned items.
    """
    from infrafoundry.core.secrets import SecretManager

    report = TailnetCleanupReport()
    if not cleanups:
        return report
    http = session or requests.Session()
    flat = SecretManager.flatten_dict(secrets or {})

    groups: dict[tuple[str, str], list[TailnetDeviceCleanup]] = {}
    for cleanup in cleanups:
        groups.setdefault((cleanup.client_id_ref, cleanup.client_secret_ref), []).append(cleanup)

    for (id_ref, secret_ref), members in groups.items():
        missing = [ref for ref in (id_ref, secret_ref) if not flat.get(ref)]
        if missing:
            report.warnings.append(
                "Tailnet cleanup skipped: secret not found: " + ", ".join(missing)
            )
            continue
        try:
            token, devices = _fetch_devices(
                http, api_base, (str(flat[id_ref]), str(flat[secret_ref])), timeout
            )
        except requests.RequestException as exc:
            report.warnings.append(
                f"Tailnet cleanup failed for {', '.join(m.hostname for m in members)}: "
                f"{type(exc).__name__}"
            )
            continue
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            report.warnings.append(
                f"Tailnet cleanup failed for {', '.join(m.hostname for m in members)}: "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        for member in members:
            matches = [d for d in devices if device_matches(d, member.hostname, member.tags)]
            if not matches:
                report.skipped.append(f"No tailnet device found for '{member.hostname}'.")
                continue
            for device in matches:
                device_id = str(device.get("id", ""))
                label = f"'{member.hostname}' (device {device_id})"
                try:
                    resp = http.delete(
                        f"{api_base}/device/{device_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=timeout,
                    )
                except requests.RequestException as exc:
                    report.warnings.append(
                        f"Could not remove tailnet device {label}: {type(exc).__name__}"
                    )
                    continue
                if 200 <= resp.status_code < 300:
                    report.removed.append(f"Removed tailnet device {label}.")
                else:
                    report.warnings.append(
                        f"Could not remove tailnet device {label}: HTTP {resp.status_code}"
                    )
    return report
