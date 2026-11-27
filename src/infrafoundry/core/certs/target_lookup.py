"""Find the host name a provider's device now serves a production certificate for.

A provider that installs through its own API (MikroTik) switches its client to full
certificate validation once the device holds an installed Let's Encrypt production
certificate. This module reads that from the declared ``certificate`` resources and their
encrypted entries; it makes no network call and never touches key material.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from infrafoundry.core.certs.install import parse_target
from infrafoundry.core.certs.models import (
    CERTIFICATE_TYPE,
    CERTS_VARIABLE,
    LETSENCRYPT_PRODUCTION,
    CertificateSchemaError,
)
from infrafoundry.core.provider import ResourceConfig


def installed_server_name(
    resources: Iterable[ResourceConfig], provider: str, now: datetime | None = None
) -> str | None:
    """Return the host name of an installed, unexpired production certificate for ``provider``.

    Args:
        resources: Every resource of the environment.
        provider: The target provider's name.
        now: The current time; defaults to the wall clock.

    Returns:
        The ``verify.server_name`` (or first plain name) of the first ``certificate`` resource
        that targets ``provider`` whose stored entry is installed, issued by the Let's Encrypt
        production directory and not expired; ``None`` when there is none.
    """
    moment = now or datetime.now(UTC)
    for resource in resources:
        if resource.provider != "acme" or resource.type != CERTIFICATE_TYPE:
            continue
        config = resource.config or {}
        target = config.get("target")
        if not isinstance(target, dict) or target.get("provider") != provider:
            continue
        if not _entry_in_service(resource, moment):
            continue
        try:
            parsed = parse_target(target, config.get("names") or ())
        except CertificateSchemaError:
            continue
        if parsed.verify_server_name:
            return parsed.verify_server_name
    return None


def _entry_in_service(resource: ResourceConfig, now: datetime) -> bool:
    certs = (resource.package_secrets or {}).get(CERTS_VARIABLE)
    entry: Any = certs.get(resource.name) if isinstance(certs, dict) else None
    if not isinstance(entry, dict):
        return False
    sha = entry.get("sha256")
    if not sha or entry.get("installed_sha256") != sha:
        return False
    if entry.get("directory") != LETSENCRYPT_PRODUCTION:
        return False
    try:
        not_after = datetime.fromisoformat(str(entry.get("not_after")))
    except ValueError:
        return False
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    return not_after > now
