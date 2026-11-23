#!/usr/bin/env python3
"""Add this ONTAP cluster to the NetApp Console through a Console agent (idempotent).

Reads ``INFRAFOUNDRY_PACKAGE_VARS`` (a JSON object of package variables, secrets
included) from the environment. No secret is taken from argv or printed.

With ``--remove`` the script instead deletes the cluster's working environment(s)
from the NetApp Console (used by the blueprint's ``on_destroy`` event, #1225).

Discovery runs only when ``console_client_id``, ``console_client_secret`` and an agent
are set. The agent is named by ``console_agent_id`` or, when that is empty, by
``console_agent_address`` (the Console agent VM's address): the script then looks the
agent ID up in the Console's agent list and uses the one active agent registered at that
address (#1629). The ``agents-mgmt`` list endpoint is undocumented; it is what the
Console web UI uses. With none of the inputs set the script logs a skip and exits 0;
with only some set it fails and names the missing ones.

Every call goes to the NetApp Console API with normal certificate verification. The
Console forwards on-prem calls to the agent named by the ``x-agent-id`` header, and
the agent connects to the cluster management address, so this host never talks to
the agent or the cluster directly.

Stdlib only (see docs/development/blueprint-script-portability.md).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

TOKEN_URL = "https://netapp-cloud-account.auth0.com/oauth/token"  # nosec B105  # OAuth endpoint URL, not a secret
TOKEN_AUDIENCE = "https://api.cloud.netapp.com"  # nosec B105  # OAuth endpoint URL, not a secret
API_URL = "https://api.bluexp.netapp.com"
ACCOUNTS_PATH = "/tenancy/account"
CONNECTORS_PATH = "/agents-mgmt/list-connectors/{account}"
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
    agent_address: str
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

    keys = (
        "console_client_id",
        "console_client_secret",
        "console_agent_id",
        "console_agent_address",
    )
    if not any(get(k) for k in keys):
        return None
    missing = [k for k in keys[:2] if not get(k)]
    if not (get("console_agent_id") or get("console_agent_address")):
        missing.append("console_agent_id or console_agent_address")
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
        agent_address=get("console_agent_address"),
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


def find_all_matching(systems: list[dict[str, Any]], cfg: Config) -> list[dict[str, Any]]:
    """Return every on-prem system :func:`find_existing` would match (name or address)."""
    matches: list[dict[str, Any]] = []
    for system in systems:
        props = system.get("ontapClusterProperties") or {}
        if system.get("name") == cfg.system_name or props.get("clusterAddress") == cfg.cluster_ip:
            matches.append(system)
    return matches


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
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310  # https endpoint from constants/package variables
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


def resolve_account(cfg: Config, token: str) -> str:
    """Return the Console account ID (configured, or the only one the token sees)."""
    if cfg.account_id:
        return cfg.account_id
    accounts = _request(API_URL + ACCOUNTS_PATH, token=token)
    return choose_one(
        "",
        accounts if isinstance(accounts, list) else [],
        "accountPublicId",
        "accountName",
        "account",
        "console_account_id",
    )


def resolve_workspace(cfg: Config, token: str) -> str:
    """Return the workspace to add the cluster to."""
    if cfg.workspace_id:
        return cfg.workspace_id
    account = resolve_account(cfg, token)
    workspaces = _request(API_URL + WORKSPACES_PATH.format(account=account), token=token)
    return choose_one(
        "",
        workspaces if isinstance(workspaces, list) else [],
        "workspacePublicId",
        "workspaceName",
        "workspace",
        "console_workspace_id",
    )


def _occms(listing: Any) -> list[dict[str, Any]]:
    """Flatten a list-connectors response into occm dicts (tolerates three shapes)."""
    entries = listing if isinstance(listing, list) else [listing]
    occms: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nested = entry.get("occms")
        if isinstance(nested, list):
            occms.extend(o for o in nested if isinstance(o, dict))
        else:
            occms.append(entry)
    return occms


def _callback_host(uri: str) -> str:
    """Return the lowercase host of a callback URI (scheme optional), or ''."""
    text = uri.strip()
    if not text:
        return ""
    try:
        return (urllib.parse.urlsplit(text if "//" in text else "//" + text).hostname or "").lower()
    except ValueError:
        return ""


def agents_at_address(listing: Any, address: str) -> list[tuple[str, str]]:
    """Return ``(agent_id, status)`` for every listed agent whose callback host is address.

    Entries with no agent ID are skipped. The host is compared exactly, not as a substring.
    """
    wanted = address.strip().lower()
    found: list[tuple[str, str]] = []
    for occm in _occms(listing):
        agent = occm.get("agent") if isinstance(occm.get("agent"), dict) else {}
        agent_id = str(agent.get("agentId") or occm.get("agentId") or "")
        if not agent_id or not wanted:
            continue
        if _callback_host(str(occm.get("primaryCallbackUri") or "")) != wanted:
            continue
        status = str(occm.get("status") or agent.get("status") or "")
        found.append((agent_id, status))
    return found


def resolve_agent(cfg: Config, token: str) -> str:
    """Return the Console agent ID: the configured one, or the active agent at the address.

    Raises:
        DiscoveryError: If no single active agent is registered at the address.
    """
    if cfg.agent_id:
        return cfg.agent_id
    account = resolve_account(cfg, token)
    listing = _request(
        API_URL + CONNECTORS_PATH.format(account=urllib.parse.quote(account, safe="")),
        token=token,
    )
    matches = agents_at_address(listing, cfg.agent_address)
    active = [agent_id for agent_id, status in matches if status == "active"]
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        raise DiscoveryError(
            f"more than one active Console agent is registered at {cfg.agent_address}; "
            "set console_agent_id to one of: " + ", ".join(active)
        )
    if not matches:
        raise DiscoveryError(
            f"no Console agent registered at {cfg.agent_address}; register the "
            "console-connector first or set console_agent_id"
        )
    listed = ", ".join(f"{agent_id} ({status or 'unknown'})" for agent_id, status in matches)
    raise DiscoveryError(
        f"no active Console agent at {cfg.agent_address}; found: {listed}. "
        "Set console_agent_id once one is active"
    )


def discover(cfg: Config) -> str:
    """Add the cluster unless the Console already has it.

    Returns:
        A one-line result message.
    """
    token = fetch_token(cfg)
    cfg = dataclasses.replace(cfg, agent_id=resolve_agent(cfg, token))
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


def remove(cfg: Config) -> str:
    """Delete every Console working environment that matches the cluster.

    Returns:
        A one-line result message.
    """
    token = fetch_token(cfg)
    cfg = dataclasses.replace(cfg, agent_id=resolve_agent(cfg, token))
    url = API_URL + ONPREM_PATH
    systems = _request(f"{url}?fields=ontapClusterProperties", token=token, agent_id=cfg.agent_id)
    matches = find_all_matching(systems if isinstance(systems, list) else [], cfg)
    if not matches:
        return f"cluster {cfg.cluster_ip} is not in the NetApp Console; nothing to do"
    removed: list[str] = []
    for system in matches:
        public_id = str(system.get("publicId") or "")
        if not public_id:
            raise DiscoveryError(f"Console system '{system.get('name')}' has no publicId")
        _request(
            f"{url}/{urllib.parse.quote(public_id, safe='')}",
            method="DELETE",
            token=token,
            agent_id=cfg.agent_id,
        )
        removed.append(f"'{system.get('name')}' ({public_id})")
    return f"removed from the NetApp Console: {', '.join(removed)}"


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (default: ``sys.argv[1:]``); ``--remove``
            deletes the cluster from the Console instead of adding it.
    """
    args = sys.argv[1:] if argv is None else argv
    removing = "--remove" in args
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
        print(f"NetApp Console discovery: {remove(cfg) if removing else discover(cfg)}")
    except DiscoveryError as exc:
        action = "removal" if removing else "discovery"
        print(f"ERROR: NetApp Console {action}: {redact(str(exc), secrets)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
