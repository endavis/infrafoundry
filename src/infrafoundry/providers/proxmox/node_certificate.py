"""Install a certificate on a Proxmox node through the node API (#1705)."""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.exceptions import APIError, AuthenticationError

from .api_client import ProxmoxClient

logger = logging.getLogger(__name__)


def _status(exc: APIError) -> int | None:
    value = exc.context.get("status_code")
    return value if isinstance(value, int) else None


def _failure(node: str, action: str, exc: APIError) -> CertificateInstallError:
    """Wrap an API error without the response text, which could echo the request."""
    status = _status(exc)
    detail = f" (HTTP {status})" if status is not None else f": {exc.message}"
    hint = ""
    if isinstance(exc, AuthenticationError) or status in (401, 403):
        hint = f"; the API token needs Sys.Modify on /nodes/{node}"
    return CertificateInstallError(f"{action} on Proxmox node '{node}' failed{detail}{hint}")


def install_node_certificate(
    client: ProxmoxClient, node: str, cert_pem: str, chain_pem: str, key_pem: str
) -> None:
    """Install a certificate and key as the node's custom certificate and restart its proxy.

    The key travels only in the POST form body. It is never logged and never put in an error.

    Args:
        client: An authenticated Proxmox API client.
        node: The Proxmox node name.
        cert_pem: The leaf certificate.
        chain_pem: The intermediate chain (may be empty).
        key_pem: The private key.

    Raises:
        CertificateInstallError: If the node does not exist or the API call fails.
    """
    try:
        listing: dict[str, Any] = client.get_json("nodes")
    except APIError as exc:
        raise _failure(node, "listing nodes", exc) from None
    known = {str(item.get("node")) for item in listing.get("data") or [] if isinstance(item, dict)}
    if node not in known:
        raise CertificateInstallError(f"Proxmox node '{node}' is not in the cluster")
    fullchain = cert_pem.rstrip("\n") + "\n" + (chain_pem.strip("\n") + "\n" if chain_pem else "")
    try:
        client.post_json(
            f"nodes/{node}/certificates/custom",
            {"certificates": fullchain, "key": key_pem, "force": 1, "restart": 1},
        )
    except APIError as exc:
        raise _failure(node, "installing the certificate", exc) from None
    logger.info("Installed a certificate on Proxmox node %s", node)
