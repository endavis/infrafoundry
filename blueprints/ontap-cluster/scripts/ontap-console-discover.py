#!/usr/bin/env python3
"""Add this ONTAP cluster to the NetApp Console through a Console agent (idempotent).

Reads ``INFRAFOUNDRY_PACKAGE_VARS`` (a JSON object of package variables, secrets
included) from the environment. No secret is taken from argv or printed.

Discovery runs only when ``console_client_id``, ``console_client_secret`` and
``console_agent_id`` are all set. With none of them set it logs a skip and exits 0;
with only some set it fails and names the missing ones.

Every call goes to the NetApp Console API with normal certificate verification. The
Console forwards on-prem calls to the agent named by the ``x-agent-id`` header, and
the agent connects to the cluster management address, so this host never talks to
the agent or the cluster directly.

Stdlib only (see docs/development/blueprint-script-portability.md).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

TOKEN_URL = "https://netapp-cloud-account.auth0.com/oauth/token"  # nosec B105
TOKEN_AUDIENCE = "https://api.cloud.netapp.com"  # nosec B105
API_URL = "https://api.bluexp.netapp.com"
ACCOUNTS_PATH = "/tenancy/account"
WORKSPACES_PATH = "/tenancy/account/{account}/workspace"
ONPREM_PATH = "/occm/api/onprem/working-environments"
TIMEOUT = 120


class DiscoveryError(Exception):
    """Raised for any failure that must stop discovery."""


@dataclass(frozen=True)
class Config:
    """Resolved discovery settings."""

    cluster_ip: str
    cluster_user: str
    cluster_password: str
    system_name: str
    client_id: str
    client_secret: str
    agent_id: str
    account_id: str
    workspace_id: str


def load_config(package_vars: dict[str, Any]) -> Config | None:
    """Build a Config from package variables.

    Args:
        package_vars: Decoded INFRAFOUNDRY_PACKAGE_VARS.

    Returns:
        A Config, or None when no discovery input is set (skip).

    Raises:
        DiscoveryError: If only some of the required inputs are set, or the
            cluster address or password is missing.
    """

    def get(key: str) -> str:
        return str(package_vars.get(key) or "").strip()

    required = ("console_client_id", "console_client_secret", "console_agent_id")
    missing = [k for k in required if not get(k)]
    if len(missing) == len(required):
        return None
    if missing:
        raise DiscoveryError("discovery is partly configured; also set: " + ", ".join(missing))
    for key in ("cluster_mgmt_ip", "ontap_password"):
        if not get(key):
            raise DiscoveryError(f"{key} is not set")
    return Config(
        cluster_ip=get("cluster_mgmt_ip"),
        cluster_user=get("console_cluster_user") or "admin",
        cluster_password=get("ontap_password"),
        system_name=get("console_system_name") or get("cluster_name"),
        client_id=get("console_client_id"),
        client_secret=get("console_client_secret"),
        agent_id=get("console_agent_id"),
        account_id=get("console_account_id"),
        workspace_id=get("console_workspace_id"),
    )


def choose_one(
    configured: str,
    items: list[dict[str, Any]],
    id_key: str,
    name_key: str,
    what: str,
    setting: str,
) -> str:
    """Return the configured ID, or the only item's ID.

    Raises:
        DiscoveryError: If none is configured and the choice is not unique.
    """
    if configured:
        return configured
    if len(items) == 1:
        return str(items[0].get(id_key) or "")
    choices = ", ".join(f"{i.get(name_key)} ({i.get(id_key)})" for i in items)
    raise DiscoveryError(
        f"cannot pick the NetApp Console {what}; set {setting} to one of: "
        + (choices or "(none returned)")
    )


def find_existing(systems: list[dict[str, Any]], cfg: Config) -> dict[str, Any] | None:
    """Return the on-prem system already registered for this cluster, if any.

    A system matches by name or by cluster management address.
    """
    for system in systems:
        if system.get("name") == cfg.system_name:
            return system
        props = system.get("ontapClusterProperties") or {}
        if props.get("clusterAddress") == cfg.cluster_ip:
            return system
    return None


def build_discover_body(cfg: Config, workspace_id: str) -> dict[str, Any]:
    """Build the on-prem working-environment request body."""
    return {
        "name": cfg.system_name,
        "description": f"ONTAP cluster {cfg.system_name} (added by InfraFoundry)",
        "location": "ON_PREM",
        "clusterAddress": cfg.cluster_ip,
        "clusterUserName": cfg.cluster_user,
        "clusterPassword": cfg.cluster_password,
        "tenantId": workspace_id,
    }


def redact(text: str, secrets: list[str]) -> str:
    """Replace every non-empty secret in ``text`` with ``***``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str = "",
    agent_id: str = "",
) -> Any:
    """Send a JSON request and return the decoded JSON body.

    Raises:
        DiscoveryError: On HTTP or network errors (message carries the API text).
    """
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if agent_id:
        headers["x-agent-id"] = agent_id
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310
            raw = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        with contextlib.suppress(ValueError, AttributeError):
            detail = str(json.loads(detail).get("message") or detail)
        raise DiscoveryError(f"HTTP {exc.code} from {method} {url}: {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise DiscoveryError(f"cannot reach {method} {url}: {exc}") from None
    try:
        return json.loads(raw)
    except ValueError:
        raise DiscoveryError(f"non-JSON response from {method} {url}") from None


def fetch_token(cfg: Config) -> str:
    """Get an API token with the client-credentials grant."""
    resp = _request(
        TOKEN_URL,
        method="POST",
        body={
            "grant_type": "client_credentials",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "audience": TOKEN_AUDIENCE,
        },
    )
    token = str(resp.get("access_token") or "") if isinstance(resp, dict) else ""
    if not token:
        raise DiscoveryError("token response had no access_token")
    return token


def resolve_workspace(cfg: Config, token: str) -> str:
    """Return the workspace to add the cluster to."""
    if cfg.workspace_id:
        return cfg.workspace_id
    accounts = _request(API_URL + ACCOUNTS_PATH, token=token)
    account = choose_one(
        cfg.account_id,
        accounts if isinstance(accounts, list) else [],
        "accountPublicId",
        "accountName",
        "account",
        "console_account_id",
    )
    workspaces = _request(API_URL + WORKSPACES_PATH.format(account=account), token=token)
    return choose_one(
        "",
        workspaces if isinstance(workspaces, list) else [],
        "workspacePublicId",
        "workspaceName",
        "workspace",
        "console_workspace_id",
    )


def discover(cfg: Config) -> str:
    """Add the cluster unless the Console already has it.

    Returns:
        A one-line result message.
    """
    token = fetch_token(cfg)
    url = API_URL + ONPREM_PATH
    # The listing leaves ontapClusterProperties (and so the address) null unless asked for.
    systems = _request(f"{url}?fields=ontapClusterProperties", token=token, agent_id=cfg.agent_id)
    existing = find_existing(systems if isinstance(systems, list) else [], cfg)
    if existing is not None:
        return (
            f"cluster {cfg.cluster_ip} is already in the NetApp Console as "
            f"'{existing.get('name')}' ({existing.get('publicId')}); nothing to do"
        )
    workspace = resolve_workspace(cfg, token)
    created = _request(
        url,
        method="POST",
        body=build_discover_body(cfg, workspace),
        token=token,
        agent_id=cfg.agent_id,
    )
    public_id = created.get("publicId") if isinstance(created, dict) else None
    return (
        f"added cluster {cfg.cluster_ip} to the NetApp Console as '{cfg.system_name}' "
        f"({public_id}) in workspace {workspace}"
    )


def main() -> int:
    """Entry point."""
    raw = os.environ.get("INFRAFOUNDRY_PACKAGE_VARS")
    if not raw:
        print("ERROR: INFRAFOUNDRY_PACKAGE_VARS is not set", file=sys.stderr)
        return 1
    package_vars = json.loads(raw)
    secrets = [
        str(package_vars.get("console_client_secret") or ""),
        str(package_vars.get("ontap_password") or ""),
    ]
    try:
        cfg = load_config(package_vars)
        if cfg is None:
            print("NetApp Console discovery: no console_* inputs set, skipping")
            return 0
        print(f"NetApp Console discovery: {discover(cfg)}")
    except DiscoveryError as exc:
        print(f"ERROR: NetApp Console discovery: {redact(str(exc), secrets)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
