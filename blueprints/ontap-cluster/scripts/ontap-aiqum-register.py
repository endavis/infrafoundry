#!/usr/bin/env python3
"""Register this ONTAP cluster with Active IQ Unified Manager (AIQUM), or remove it.

Reads ``INFRAFOUNDRY_PACKAGE_VARS`` (a JSON object of package variables, secrets
included) from the environment. No secret is taken from argv or printed.

Runs only when ``aiqum_address`` and ``aiqum_admin_password`` are both set. With
neither set it logs a skip and exits 0; with only one set it fails and names the
missing input.

Without arguments the script adds the cluster as an AIQUM data source unless one
already matches by address or name. With ``--remove`` it deletes every matching
data source (used by the blueprint's ``on_destroy`` event, #1225).

The AIQUM client is copied from ``blueprints/aiqum/scripts/aiqum-initial-setup.py``,
not imported: each blueprint's ``scripts/`` directory is synced on its own.

Stdlib only (see docs/development/blueprint-script-portability.md).
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError

CLUSTERS_PATH = "/api/admin/datasources/clusters"
TIMEOUT = 30
# Adding a cluster returns only after AIQUM has set up its agent link to the
# cluster: 12 s when it works, 86 s when the cluster cannot reach AIQUM (#1167).
ADD_TIMEOUT = 180


class AIQUMError(Exception):
    """Raised for any failure that must stop registration."""


@dataclass(frozen=True)
class Config:
    """Resolved registration settings."""

    aiqum_address: str
    admin_user: str
    admin_password: str
    cluster_ip: str
    cluster_name: str
    cluster_user: str
    cluster_password: str
    ca_cert: str = ""
    tls_insecure: bool = False
    scheme: str = "https"


def load_config(package_vars: dict[str, Any]) -> Config | None:
    """Build a Config from package variables.

    Args:
        package_vars: Decoded INFRAFOUNDRY_PACKAGE_VARS.

    Returns:
        A Config, or None when no AIQUM input is set (skip).

    Raises:
        AIQUMError: If only one of ``aiqum_address`` / ``aiqum_admin_password`` is
            set, or the cluster address or password is missing.
    """

    def get(key: str) -> str:
        return str(package_vars.get(key) or "").strip()

    required = ("aiqum_address", "aiqum_admin_password")
    missing = [k for k in required if not get(k)]
    if len(missing) == len(required):
        return None
    if missing:
        raise AIQUMError("AIQUM registration is partly configured; also set: " + ", ".join(missing))
    for key in ("cluster_mgmt_ip", "ontap_password"):
        if not get(key):
            raise AIQUMError(f"{key} is not set")
    return Config(
        aiqum_address=get("aiqum_address"),
        admin_user=get("aiqum_admin_user") or "umadmin",
        admin_password=get("aiqum_admin_password"),
        cluster_ip=get("cluster_mgmt_ip"),
        cluster_name=get("cluster_name"),
        cluster_user=get("aiqum_cluster_user") or "admin",
        cluster_password=get("ontap_password"),
        ca_cert=get("aiqum_ca_cert"),
        tls_insecure=get("aiqum_tls_insecure").lower() in ("1", "true", "yes"),
    )


def make_ssl_context(cfg: Config) -> ssl.SSLContext:
    """Build the SSL context for talking to AIQUM.

    The certificate is verified by default, against ``aiqum_ca_cert`` when it is
    set (a PEM file that trusts AIQUM's self-signed certificate) and against the
    system trust store otherwise. Verification is off only when
    ``aiqum_tls_insecure`` is explicitly true, because the request carries the
    AIQUM admin and ONTAP passwords.

    Args:
        cfg: Resolved settings.

    Returns:
        The ``ssl.SSLContext`` to use.

    Raises:
        AIQUMError: If ``aiqum_ca_cert`` cannot be loaded.
    """
    if cfg.tls_insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # nosec B501 - explicit aiqum_tls_insecure opt-in
        ctx.verify_mode = ssl.CERT_NONE  # nosec B501 - explicit aiqum_tls_insecure opt-in
        return ctx
    try:
        return ssl.create_default_context(cafile=cfg.ca_cert or None)
    except (OSError, ssl.SSLError) as exc:
        raise AIQUMError(f"cannot load aiqum_ca_cert {cfg.ca_cert}: {exc}") from None


def redact(text: str, secrets: list[str]) -> str:
    """Replace every non-empty secret in ``text`` with ``***``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _request(
    cfg: Config,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: int = TIMEOUT,
) -> tuple[int, Any]:
    """Send a Basic-auth JSON request to AIQUM.

    Returns:
        ``(status, decoded_body)``; the body is ``{}`` when empty.

    Raises:
        AIQUMError: On a non-2xx status (except 409, returned to the caller) or a
            network error.
    """
    url = f"{cfg.scheme}://{cfg.aiqum_address}{path}"
    token = base64.b64encode(f"{cfg.admin_user}:{cfg.admin_password}".encode()).decode("ascii")
    headers = {"Accept": "application/json", "Authorization": f"Basic {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(  # nosec B310 - URL built from package variables
            req, context=make_ssl_context(cfg), timeout=timeout
        ) as resp:
            status, raw = resp.status, resp.read()
    except HTTPError as exc:
        status, raw = exc.code, (exc.read() if exc.fp else b"")
        if status != 409:
            raise AIQUMError(
                f"HTTP {status} from {method} {url}: {raw.decode(errors='replace')}"
            ) from None
    except (URLError, OSError) as exc:
        raise AIQUMError(f"cannot reach {method} {url}: {exc}") from None
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, {"_raw": raw.decode(errors="replace")}


def list_clusters(cfg: Config) -> list[dict[str, Any]]:
    """Return AIQUM's cluster data sources."""
    _, body = _request(cfg, "GET", CLUSTERS_PATH)
    records = body.get("records") if isinstance(body, dict) else body
    return [r for r in records or [] if isinstance(r, dict)]


def find_matching(clusters: list[dict[str, Any]], cfg: Config) -> list[dict[str, Any]]:
    """Return the data sources whose address or name matches this cluster."""
    return [
        c
        for c in clusters
        if c.get("address") == cfg.cluster_ip
        or (cfg.cluster_name and c.get("name") == cfg.cluster_name)
    ]


def build_add_body(cfg: Config) -> dict[str, Any]:
    """Build the add-data-source request body."""
    return {
        "address": cfg.cluster_ip,
        "username": cfg.cluster_user,
        "password": cfg.cluster_password,
        "port": 443,
        "protocol": "https",
    }


def register(cfg: Config) -> str:
    """Add the cluster unless AIQUM already has it.

    Returns:
        A one-line result message.
    """
    existing = find_matching(list_clusters(cfg), cfg)
    if existing:
        return (
            f"cluster {cfg.cluster_ip} is already an AIQUM data source "
            f"('{existing[0].get('name')}'); nothing to do"
        )
    status, _ = _request(cfg, "POST", CLUSTERS_PATH, body=build_add_body(cfg), timeout=ADD_TIMEOUT)
    if status == 409:
        return f"cluster {cfg.cluster_ip} already exists in AIQUM; nothing to do"
    return f"added cluster {cfg.cluster_ip} to AIQUM at {cfg.aiqum_address}"


def remove(cfg: Config) -> str:
    """Delete every AIQUM data source that matches the cluster.

    Returns:
        A one-line result message.
    """
    matches = find_matching(list_clusters(cfg), cfg)
    if not matches:
        return f"cluster {cfg.cluster_ip} is not in AIQUM; nothing to do"
    removed: list[str] = []
    for cluster in matches:
        key = str(cluster.get("key") or "")
        if not key:
            raise AIQUMError(f"AIQUM data source '{cluster.get('name')}' has no key")
        _request(cfg, "DELETE", f"{CLUSTERS_PATH}/{urllib.parse.quote(key, safe='')}")
        removed.append(f"'{cluster.get('name')}' ({key})")
    return f"removed from AIQUM: {', '.join(removed)}"


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (default: ``sys.argv[1:]``); ``--remove``
            deletes the cluster from AIQUM instead of adding it.
    """
    args = sys.argv[1:] if argv is None else argv
    removing = "--remove" in args
    raw = os.environ.get("INFRAFOUNDRY_PACKAGE_VARS")
    if not raw:
        print("ERROR: INFRAFOUNDRY_PACKAGE_VARS is not set", file=sys.stderr)
        return 1
    package_vars = json.loads(raw)
    secrets = [
        str(package_vars.get("aiqum_admin_password") or ""),
        str(package_vars.get("ontap_password") or ""),
    ]
    try:
        cfg = load_config(package_vars)
        if cfg is None:
            print("AIQUM registration: no aiqum_* inputs set, skipping")
            return 0
        print(f"AIQUM registration: {remove(cfg) if removing else register(cfg)}")
    except AIQUMError as exc:
        action = "removal" if removing else "registration"
        print(f"ERROR: AIQUM {action}: {redact(str(exc), secrets)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
