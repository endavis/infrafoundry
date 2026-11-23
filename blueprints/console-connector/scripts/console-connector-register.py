#!/usr/bin/env python3
"""Register a NetApp Console agent with the NetApp Console (idempotent).

Reads ``INFRAFOUNDRY_PACKAGE_VARS`` (a JSON object of package variables, secrets
included) from the environment. No secret is taken from argv or printed.

Registration runs only when ``console_client_id``, ``console_client_secret`` and
``console_admin_email`` are all set. With none of them set it logs a skip and
exits 0; with only some set it fails and names the missing ones.

With ``--remove`` the script instead deregisters the agent from the Console (used by
the blueprint's ``on_destroy`` event, #1629): it lists the Console's agents, picks every
one whose callback address host equals ``ip_address`` and deletes it. It makes Console
calls only, so it needs no ``--agent-cert``. The ``agents-mgmt`` endpoints are
undocumented; they are what the Console web UI uses.

Every request to the agent is TLS-pinned to the agent's own certificate, passed as
a PEM file path with ``--agent-cert``, so neither the bearer token nor the setup
status is exchanged with any other server.

Stdlib only (see docs/development/blueprint-script-portability.md).
"""

from __future__ import annotations

import contextlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOKEN_URL = "https://netapp-cloud-account.auth0.com/oauth/token"  # nosec B105  # OAuth endpoint URL, not a secret
TOKEN_AUDIENCE = "https://api.cloud.netapp.com"  # nosec B105  # OAuth endpoint URL, not a secret
ACCOUNTS_URL = "https://api.bluexp.netapp.com/tenancy/account"
CONNECTORS_URL = "https://api.bluexp.netapp.com/agents-mgmt/list-connectors"
AGENT_MGMT_URL = "https://api.bluexp.netapp.com/agents-mgmt/agent"
AGENT_URL_TEMPLATE = "https://{ip}/occm/api/occm"
TIMEOUT = 30
PORTAL_POLL_INTERVAL = 2.0
PORTAL_POLL_TIMEOUT = 60.0

ADMIN_HINT = (
    "The service account needs an admin role (e.g. Organization admin) on the "
    "NetApp Console organization."
)
_ADMIN_ERROR = "not associated as admin"


class RegistrationError(Exception):
    """Raised for any failure that must stop registration."""


@dataclass(frozen=True)
class Config:
    """Resolved registration settings."""

    ip: str
    client_id: str
    client_secret: str
    admin_email: str
    account_id: str
    company: str
    site: str


def load_config(package_vars: dict[str, Any]) -> Config | None:
    """Build a Config from package variables.

    Args:
        package_vars: Decoded INFRAFOUNDRY_PACKAGE_VARS.

    Returns:
        A Config, or None when no registration input is set (skip).

    Raises:
        RegistrationError: If only some of the required inputs are set.
    """

    def get(key: str) -> str:
        return str(package_vars.get(key) or "").strip()

    required = ("console_client_id", "console_client_secret", "console_admin_email")
    missing = [k for k in required if not get(k)]
    if len(missing) == len(required):
        return None
    if missing:
        raise RegistrationError(
            "registration is partly configured; also set: " + ", ".join(missing)
        )
    ip = get("ip_address")
    if not ip:
        raise RegistrationError("ip_address is not set")
    return Config(
        ip=ip,
        client_id=get("console_client_id"),
        client_secret=get("console_client_secret"),
        admin_email=get("console_admin_email"),
        account_id=get("console_account_id"),
        company=get("console_company") or get("vm_name") or "infrafoundry",
        site=get("console_site") or "default",
    )


def parse_setup_status(payload: dict[str, Any]) -> tuple[bool, str]:
    """Extract (is_setup, account_id) from a support-services response."""
    is_setup = bool((payload.get("setupInfo") or {}).get("isSetup"))
    account = str((payload.get("tenancyServiceInformation") or {}).get("accountId") or "")
    return is_setup, account


def needs_portal_register(payload: dict[str, Any]) -> bool:
    """True when the agent has no Console login (auth0 client ID) yet."""
    portal = payload.get("portalService") or {}
    auth0 = portal.get("auth0Information") or {}
    return not str(auth0.get("clientId") or "").strip()


def choose_account(configured: str, accounts: list[dict[str, Any]]) -> str:
    """Pick the tenancy account ID.

    Raises:
        RegistrationError: If none is configured and the choice is not unique.
    """
    if configured:
        return configured
    if len(accounts) == 1:
        return str(accounts[0].get("accountPublicId") or "")
    choices = ", ".join(f"{a.get('accountName')} ({a.get('accountPublicId')})" for a in accounts)
    raise RegistrationError(
        "cannot pick the NetApp Console account; set console_account_id to one of: "
        + (choices or "(none returned)")
    )


def build_register_body(cfg: Config, account_id: str) -> dict[str, Any]:
    """Build the setup-portal/init request body."""
    return {
        "adminUser": {"email": cfg.admin_email},
        "company": cfg.company,
        "site": cfg.site,
        "tenancyAccountId": account_id,
    }


def explain_error(message: str) -> str:
    """Add a hint to known registration error messages."""
    if _ADMIN_ERROR in message:
        return f"{message}. {ADMIN_HINT}"
    return message


def redact(text: str, secrets: list[str]) -> str:
    """Replace every non-empty secret in text with ***."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def pinned_context(pem: str) -> ssl.SSLContext:
    """TLS context that trusts exactly one (self-signed) certificate.

    Raises:
        RegistrationError: If pem is empty or not a certificate.
    """
    if "BEGIN CERTIFICATE" not in pem:
        raise RegistrationError("agent certificate pin is empty or not a PEM certificate")
    try:
        ctx = ssl.create_default_context(cadata=pem)
    except (ssl.SSLError, ValueError) as exc:
        raise RegistrationError(f"agent certificate pin is invalid: {exc}") from None
    ctx.verify_mode = ssl.CERT_REQUIRED
    # The trust anchor is the one self-signed cert itself; its name is not checked.
    ctx.check_hostname = False
    return ctx


def load_pin(path: str) -> str:
    """Read the pinned agent certificate PEM from path (fail closed)."""
    if not path:
        raise RegistrationError("--agent-cert <pem file> is required for registration")
    try:
        pem = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistrationError(f"cannot read agent certificate pin {path}: {exc}") from None
    pinned_context(pem)
    return pem


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str = "",
    pin: str = "",
) -> Any:
    """Send a JSON request and return the decoded JSON body.

    Raises:
        RegistrationError: On HTTP or network errors (message carries the API text).
    """
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = pinned_context(pin) if pin else None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:  # nosec B310  # https endpoint from constants/package variables
            raw = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        with contextlib.suppress(ValueError, AttributeError):
            detail = str(json.loads(detail).get("message") or detail)
        raise RegistrationError(f"HTTP {exc.code} from {method} {url}: {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise RegistrationError(f"cannot reach {method} {url}: {exc}") from None
    try:
        return json.loads(raw)
    except ValueError:
        raise RegistrationError(f"non-JSON response from {method} {url}") from None


def get_support_services(cfg: Config, pin: str) -> dict[str, Any]:
    """Read the agent's support-services document, pinned to the agent certificate."""
    base = AGENT_URL_TEMPLATE.format(ip=cfg.ip)
    payload = _request(f"{base}/system/support-services", pin=pin)
    return payload if isinstance(payload, dict) else {}


def get_status(cfg: Config, pin: str) -> tuple[bool, str]:
    """Read the agent's setup status, trusting only the pinned agent certificate."""
    return parse_setup_status(get_support_services(cfg, pin))


def ensure_portal_registered(cfg: Config, pin: str, payload: dict[str, Any]) -> None:
    """Run the agent's own register step when it has no Console login yet.

    A fresh agent has no ``portalService.auth0Information.clientId`` and refuses
    ``setup-portal/init`` until it has one. HTTP 409 means the step already ran.

    Raises:
        RegistrationError: If the register call fails or the client ID never appears.
    """
    if not needs_portal_register(payload):
        return
    base = AGENT_URL_TEMPLATE.format(ip=cfg.ip)
    try:
        _request(f"{base}/setup-portal/register", method="POST", pin=pin)
    except RegistrationError as exc:
        if "HTTP 409" not in str(exc):
            raise
    deadline = time.monotonic() + PORTAL_POLL_TIMEOUT
    while True:
        if not needs_portal_register(get_support_services(cfg, pin)):
            return
        if time.monotonic() >= deadline:
            raise RegistrationError(
                "agent did not report a Console login (auth0 client ID) after its register step"
            )
        time.sleep(PORTAL_POLL_INTERVAL)


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
        raise RegistrationError("token response had no access_token")
    return token


def register(cfg: Config, pin: str) -> str:
    """Run the registration flow.

    Args:
        cfg: Registration settings.
        pin: PEM of the agent certificate; trusted for the authenticated call.

    Returns:
        "already-registered" or "registered".

    Raises:
        RegistrationError: On any failure.
    """
    pinned_context(pin)  # fail closed before any request
    status = get_support_services(cfg, pin)
    is_setup, _ = parse_setup_status(status)
    if is_setup:
        return "already-registered"
    ensure_portal_registered(cfg, pin, status)
    token = fetch_token(cfg)
    accounts: list[dict[str, Any]] = []
    if not cfg.account_id:
        listed = _request(ACCOUNTS_URL, token=token)
        accounts = listed if isinstance(listed, list) else []
    account_id = choose_account(cfg.account_id, accounts)
    base = AGENT_URL_TEMPLATE.format(ip=cfg.ip)
    try:
        _request(
            f"{base}/setup-portal/init",
            method="POST",
            body=build_register_body(cfg, account_id),
            token=token,
            pin=pin,
        )
    except RegistrationError as exc:
        raise RegistrationError(explain_error(str(exc))) from None
    is_setup, account = get_status(cfg, pin)
    if not is_setup or account != account_id:
        raise RegistrationError(
            f"agent did not report registration to account {account_id} after init"
        )
    return "registered"


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


def deregister(cfg: Config) -> str:
    """Remove every Console agent registered at ``cfg.ip``.

    Returns:
        A one-line result message.

    Raises:
        RegistrationError: On any failure; a refused DELETE names the agent ID.
    """
    token = fetch_token(cfg)
    account = cfg.account_id
    if not account:
        listed = _request(ACCOUNTS_URL, token=token)
        account = choose_account("", listed if isinstance(listed, list) else [])
    listing = _request(f"{CONNECTORS_URL}/{urllib.parse.quote(account, safe='')}", token=token)
    matches = agents_at_address(listing, cfg.ip)
    if not matches:
        return f"no Console agent registered at {cfg.ip}; nothing to do"
    removed: list[str] = []
    for agent_id, _status in matches:
        try:
            _request(
                f"{AGENT_MGMT_URL}/{urllib.parse.quote(agent_id, safe='')}",
                method="DELETE",
                token=token,
            )
        except RegistrationError as exc:
            raise RegistrationError(
                f"{redact(str(exc), [token])}. Remove agent {agent_id} in the NetApp Console under "
                "Agents > Manage agents"
            ) from None
        removed.append(agent_id)
    return "removed Console agent(s): " + ", ".join(removed)


def _agent_cert_arg(argv: list[str]) -> str:
    """Return the value of --agent-cert from argv, or ''."""
    for i, arg in enumerate(argv):
        if arg == "--agent-cert" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--agent-cert="):
            return arg.split("=", 1)[1]
    return ""


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    args = sys.argv[1:] if argv is None else argv
    removing = "--remove" in args
    raw = os.environ.get("INFRAFOUNDRY_PACKAGE_VARS", "")
    if not raw:
        print("ERROR: INFRAFOUNDRY_PACKAGE_VARS is not set", file=sys.stderr)
        return 1
    try:
        package_vars = json.loads(raw)
        cfg = load_config(package_vars)
    except (ValueError, RegistrationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if cfg is None:
        action = "Deregistration" if removing else "Registration"
        print(f"  {action} skipped: console_client_id/secret/admin_email not set")
        return 0
    secrets = [cfg.client_secret, cfg.client_id]
    if removing:
        try:
            print(f"  {deregister(cfg)}")
        except RegistrationError as exc:
            print(
                f"ERROR: Console agent deregistration: {redact(str(exc), secrets)}", file=sys.stderr
            )
            return 1
        return 0
    try:
        pin = load_pin(_agent_cert_arg(args))
        result = register(cfg, pin)
    except RegistrationError as exc:
        print(f"ERROR: {redact(str(exc), secrets)}", file=sys.stderr)
        return 1
    print(f"  Console agent {result.replace('-', ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
