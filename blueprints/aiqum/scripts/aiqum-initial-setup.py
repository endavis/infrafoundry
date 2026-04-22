#!/usr/bin/env python3
"""AIQUM First Experience Wizard (FEW) automation.

Automates the initial setup wizard that runs on first login to AIQUM.
Uses Basic auth and the management-server REST API.

This script is stdlib-only (no `requests`, no `PyYAML`) so it can run on
minimal jumphosts where only `python3` and the portable baseline are
guaranteed available. See docs/development/blueprint-script-portability.md.

Steps:
  1. Configure email/SMTP notification
  2. Accept AutoSupport
  3. Change admin password
  4. Enable API Gateway
  5. Add ONTAP cluster
  6. Mark setup complete
  7. Create default alert policy (if aiqum_alert_email set)
  8. Send test alert email (if alert created)
"""

from __future__ import annotations

import base64
import json
import os
import smtplib
import ssl
import sys
import urllib.parse
from email.mime.text import MIMEText
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HAL_JSON = "application/vnd.netapp.v1.hal+json"
DEFAULT_PASSWORD = "admin"  # nosec B105 - initial FEW password published in NetApp docs

DEFAULT_ALERT_SEVERITIES = ["critical", "error", "warning"]

DEFAULT_ALERT_EVENT_TYPES = [
    "Cluster Monitoring Failed",
    "Some Unassigned Disks",
    "Cluster Lacks Spare Disks",
    "Some Failed Disks",
    "Cluster Not Reachable",
    "Protection Job Failed",
    "Space In Audit Volume Almost Full",
    "MetroCluster Spare Disks Left Behind",
    "Flash Disks - Spare Blocks Almost Consumed",
    "Flash Disks - No Spare Blocks",
    "Some Unsupported Disks",
    "MetroCluster Automatic Unplanned Switchover Disabled",
    "Critical EMS received",
    "Warning EMS received",
    "Error EMS received",
    "Informational EMS received",
    "Notice EMS received",
    "Debug EMS received",
    "Emergency EMS received",
    "Alert EMS received",
    "Cluster IOPS Critical Threshold Breached",
    "Cluster IOPS Warning Threshold Breached",
    "Cluster MB/s Critical Threshold Breached",
    "Cluster MB/s Warning Threshold Breached",
    "Cluster FabricPool License Capacity Limits Exceeded",
    "Object Maintenance Window Started",
    "Cluster Cloud Tier Planning",
    "FabricPool Space Nearly Full",
    "NVMe-oF Grace Period Started",
    "NVMe-oF Grace Period Active",
    "NVMe-oF Grace Period Expired",
    "Cluster Load Imbalance Threshold Breached",
    "NTP server count is low",
    "FIPS Mode Disabled",
    "Telnet Protocol Enabled",
    "Default local admin user enabled",
    "Log Forwarding Not Encrypted",
    "Login Banner Disabled",
    "SSH is using insecure ciphers",
    "Cluster Peer Communication Not Encrypted",
    "AutoSupport HTTPS transport disabled",
    "Cluster Capacity Imbalance Threshold Breached",
    "Cluster Login Banner Changed",
    "Cluster Log Forwarding Destinations Changed",
    "Cluster NTP Server Names Changed",
    "Remote Shell is Enabled on the cluster",
    "Cluster uses a self-signed certificate",
    "Passwords of some ONTAP user accounts use the less secure MD5 hash function",
    "Cluster Certificate Expired",
    "Cluster Certificate About to Expire",
    "Mutual TLS Certificate Expired",
    "Mutual TLS Certificate About to Expire",
    "Controller Susceptible To Bug 509721",
    "Controller Susceptible To Bug 677849",
    "Cluster HA Configuration Is Not Set",
    "ONTAP Version Mismatch",
    "Controller Has Only One Cluster LIF",
    "Unsupported HA Interconnect Cables",
    "Cluster Health Is Intact",
    "Advisory ID: NTAP-20170331-0002",
    "Advisory ID: NTAP-20160722-0001",
    "CN1610 FastPath OS Is In Limited Support",
]


def make_ssl_context() -> ssl.SSLContext:
    """Build a permissive SSL context for AIQUM's self-signed FEW certificate.

    The freshly deployed AIQUM appliance ships with a self-signed cert that
    cannot be validated. FEW automation by definition runs before the operator
    has had a chance to install a trusted cert, so we disable verification.

    Returns:
        An ``ssl.SSLContext`` that does not validate the peer certificate.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class AIQUMClient:
    """Minimal Basic-auth JSON client for the AIQUM management-server REST API.

    Wraps ``urllib.request`` to provide the subset of HTTP verbs needed by the
    FEW automation (GET/POST/PUT). Uses stdlib only so it runs on minimal
    jumphosts where ``requests`` is not installed.

    Attributes:
        base_url: AIQUM base URL (e.g. ``https://192.168.1.50``).
    """

    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        ssl_context: ssl.SSLContext,
        timeout: int = 30,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: AIQUM base URL, no trailing slash.
            user: Basic auth username.
            password: Basic auth password.
            ssl_context: SSL context (usually from :func:`make_ssl_context`).
            timeout: Per-request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self._ssl_ctx = ssl_context
        self._timeout = timeout
        self._auth_header = self._encode_basic_auth(user, password)

    @staticmethod
    def _encode_basic_auth(user: str, password: str) -> str:
        """Build a ``Basic <b64>`` Authorization header value."""
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        return f"Basic {token}"

    def set_auth(self, user: str, password: str) -> None:
        """Replace the Basic auth credentials on an existing client.

        Used after Step 3 (password change) so subsequent requests use the
        new password without rebuilding the client.

        Args:
            user: New Basic auth username.
            password: New Basic auth password.
        """
        self._auth_header = self._encode_basic_auth(user, password)

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any]]:
        """Dispatch a single HTTP request and parse the response.

        Args:
            method: HTTP verb (``GET``, ``POST``, ``PUT``).
            path: Path portion of the URL, starting with ``/``.
            body: Optional body object, serialized to JSON.
            params: Optional query-string parameters.
            content_type: ``Content-Type`` header for the request body.

        Returns:
            A tuple ``(status_code, parsed_body)``. ``parsed_body`` is a dict
            parsed from the JSON response, or ``{}`` if the response had no
            body, or ``{"_raw": "<text>"}`` if the body was not valid JSON.
            HTTPError responses are *not* re-raised — their status and body
            are returned so callers can branch on status.
        """
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth_header)
        if data is not None:
            req.add_header("Content-Type", content_type)

        try:
            with urlopen(  # nosec B310 - AIQUM URL constructed from package variables
                req, context=self._ssl_ctx, timeout=self._timeout
            ) as resp:
                raw = resp.read()
                return resp.status, self._parse_body(raw)
        except HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            return exc.code, self._parse_body(raw)

    @staticmethod
    def _parse_body(raw: bytes) -> dict[str, Any]:
        """Parse a response body as JSON, falling back to raw text."""
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"_raw": raw.decode("utf-8", errors="replace")}
        if isinstance(decoded, dict):
            return decoded
        return {"_raw": decoded}

    def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """Issue a GET request."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        body: Any,
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any]]:
        """Issue a POST request with a JSON body."""
        return self._request("POST", path, body=body, content_type=content_type)

    def put(
        self,
        path: str,
        body: Any,
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any]]:
        """Issue a PUT request with a JSON body."""
        return self._request("PUT", path, body=body, content_type=content_type)


def load_config() -> dict[str, Any]:
    """Load package variables from the ``INFRAFOUNDRY_PACKAGE_VARS`` env var.

    The ScriptHandler sets this variable to the JSON-encoded package
    variables before invoking blueprint scripts. Direct invocation (not via
    ``foundry infra apply``) is no longer supported — the yaml-based
    fallback was removed in #644 as part of the stdlib-only rewrite.

    Returns:
        Parsed package variables dict.

    Raises:
        RuntimeError: If ``INFRAFOUNDRY_PACKAGE_VARS`` is unset or empty.
    """
    env_vars = os.environ.get("INFRAFOUNDRY_PACKAGE_VARS")
    if not env_vars:
        raise RuntimeError(
            "INFRAFOUNDRY_PACKAGE_VARS is not set -- run via 'foundry infra apply', "
            "not directly. The yaml-based fallback was removed in #644."
        )
    return json.loads(env_vars)


def save_option(client: AIQUMClient, name: str, value: str | int | bool) -> bool:
    """Save a single option via the management-server admin API.

    Args:
        client: Authenticated AIQUM client.
        name: Option name (e.g. ``autosupport.enabled``).
        value: Option value.

    Returns:
        True if AIQUM accepted the option (2xx status), False otherwise.
    """
    code, _ = client.post(
        "/api/management-server/admin/options",
        body={"options": [{"name": name, "value": value}]},
        content_type=HAL_JSON,
    )
    if code in (200, 201, 204):
        return True
    # Avoid logging response body -- may contain sensitive data
    print(f"    Failed to set {name}: {code}")
    return False


def create_alert(client: AIQUMClient, name: str, email: str) -> bool:
    """Create a default alert policy via the management-server API.

    Args:
        client: Authenticated AIQUM client.
        name: Display name for the alert policy.
        email: Recipient email address for notifications.

    Returns:
        True on success or if the alert already exists (409), False otherwise.
    """
    payload = {
        "name": name,
        "enabled": True,
        "action": {
            "notification": {
                "emails": [email],
                "send_snmp_trap": False,
            }
        },
        "resource": [{"type": "cluster", "include_all": True}],
        "event": {
            "severities": DEFAULT_ALERT_SEVERITIES,
            "types": DEFAULT_ALERT_EVENT_TYPES,
        },
    }
    code, _ = client.post("/api/management-server/alerts", body=payload)
    if code in (200, 201):
        return True
    if code == 409:
        print("    Alert already exists (OK)")
        return True
    print(f"    Failed to create alert: {code}")
    return False


def send_test_email(config: dict[str, Any], recipient: str) -> bool:
    """Send a test email via SMTP to verify the alert delivery path.

    Uses the same SMTP settings configured in Step 1 to send a short
    verification message to the alert recipient.

    Args:
        config: Package variables dict with smtp_server, smtp_port,
            smtp_user, smtp_password, and aiqum_admin_email.
        recipient: Email address to send the test to.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    msg = MIMEText(
        "This is a test email from the AIQUM initial setup wizard.\n\n"
        "If you received this message, alert email delivery is working.\n"
    )
    msg["Subject"] = f"[AIQUM] Test alert email from {config.get('ip_address', 'unknown')}"
    msg["From"] = config["aiqum_admin_email"]
    msg["To"] = recipient

    try:
        with smtplib.SMTP(config["smtp_server"], int(config["smtp_port"]), timeout=30) as srv:
            srv.starttls()
            srv.login(config["smtp_user"], config["smtp_password"])
            srv.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - report any SMTP failure as non-fatal
        print(f"    SMTP error: {exc}")
        return False


def main() -> int:  # noqa: C901, PLR0911, PLR0912, PLR0915 - wizard is inherently linear
    """Run the First Experience Wizard against a freshly deployed AIQUM VM.

    Returns:
        0 on success, 1 on any fatal step failure.
    """
    config = load_config()
    base_url = f"https://{config['ip_address']}"
    new_password = config["aiqum_admin_password"]
    user = config["aiqum_admin_user"]

    print("=== AIQUM Initial Setup (First Experience Wizard) ===")
    print(f"  Target: {base_url}")

    client = AIQUMClient(base_url, user, DEFAULT_PASSWORD, make_ssl_context())

    # Determine current password
    code, _ = client.get(
        "/api/management-server/admin/options",
        params={"option": "autosupport.enabled"},
    )
    if code == 401:
        client.set_auth(user, new_password)
        code, _ = client.get(
            "/api/management-server/admin/options",
            params={"option": "autosupport.enabled"},
        )
        if code == 401:
            print("  ERROR: Cannot authenticate with default or configured password")
            return 1
        print("  Authenticated with configured password (setup may be partial)")
        password_already_changed = True
    else:
        print("  Authenticated with default password")
        password_already_changed = False

    # Step 1: Email/SMTP
    print("\nStep 1: Configuring email and SMTP...")
    smtp_options: dict[str, str | int | bool] = {
        "email.fromAddress": config["aiqum_admin_email"],
        "mail.smtp.host": config["smtp_server"],
        "mail.smtp.port": config["smtp_port"],
        "mail.smtp.starttls": "true",
        "mail.smtp.username": config["smtp_user"],
        "mail.smtp.password": config["smtp_password"],
    }
    all_ok = True
    for name, value in smtp_options.items():
        if not save_option(client, name, value):
            all_ok = False
    print(f"  Email/SMTP: {'OK' if all_ok else 'PARTIAL (check above)'}")

    # Step 2: AutoSupport
    print("\nStep 2: Enabling AutoSupport...")
    if save_option(client, "autosupport.enabled", "true"):
        print("  AutoSupport: OK")
    else:
        print("  AutoSupport: FAILED")
        return 1

    # Step 3: Change password
    print("\nStep 3: Changing admin password...")
    if password_already_changed:
        print("  Skipped (already using configured password)")
    else:
        code, body = client.put(
            "/api/management-server/admin/users/current/password",
            body={
                "currentPassword": DEFAULT_PASSWORD,
                "newPassword": new_password,
                "confirmPassword": new_password,
            },
            content_type=HAL_JSON,
        )
        if code in (200, 201, 204):
            print("  Password: OK")
            client.set_auth(user, new_password)
        else:
            # Avoid logging full response body; _raw field is a best-effort snippet
            snippet = str(body.get("_raw", ""))[:200] if body else ""
            print(f"  Password: FAILED ({code}) {snippet}")
            return 1

    # Step 4: API Gateway
    print("\nStep 4: Enabling API Gateway...")
    if save_option(client, "api.gateway.enabled", "true"):
        print("  API Gateway: OK")
    else:
        print("  API Gateway: FAILED")
        return 1

    # Step 5: Add ONTAP cluster
    print(f"\nStep 5: Adding ONTAP cluster ({config['ontap_cluster_ip']})...")
    code, body = client.post(
        "/api/admin/datasources/clusters",
        body={
            "address": config["ontap_cluster_ip"],
            "username": config["ontap_admin_user"],
            "password": config["ontap_admin_password"],
            "port": 443,
            "protocol": "https",
        },
    )
    if code in (200, 201):
        print("  Cluster: OK")
    elif code == 409:
        print("  Cluster: Already exists (OK)")
    else:
        print(f"  Cluster: {code} (non-fatal)")
        # Best-effort detail extraction; mirrors the old behavior of the .text fallback
        message = ""
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = str(error.get("message", ""))
            if not message:
                message = str(body.get("_raw", ""))[:200]
        print(f"    {message}")

    # Step 6: Mark setup complete
    print("\nStep 6: Marking initial setup complete...")
    if save_option(client, "initialSetupComplete", True):
        print("  Setup complete: OK")
    else:
        print("  Setup complete: FAILED")
        return 1

    # Step 7: Create default alert policy
    alert_email = config.get("aiqum_alert_email", "")
    if alert_email:
        alert_name = f"Alerts to {alert_email}"
        print("\nStep 7: Creating default alert policy...")
        if create_alert(client, alert_name, alert_email):
            print(f"  Alert: OK ({alert_name})")
            # Step 8: Send test email
            print("\nStep 8: Sending test alert email...")
            if send_test_email(config, alert_email):
                print(f"  Test email: OK (sent to {alert_email})")
            else:
                print("  Test email: FAILED (non-fatal)")
        else:
            print("  Alert: FAILED (non-fatal)")
    else:
        print("\nStep 7: Skipping alert setup (aiqum_alert_email not set)")

    print("\n=== AIQUM Initial Setup Complete ===")
    print(f"  URL: {base_url}/")
    print(f"  User: {user}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
