#!/usr/bin/env python3
"""AIQUM First Experience Wizard (FEW) automation.

Automates the initial setup wizard that runs on first login to AIQUM.
Uses Basic auth and the management-server REST API.

Steps:
  1. Configure email/SMTP notification
  2. Accept AutoSupport
  3. Change admin password
  4. Enable API Gateway
  5. Add ONTAP cluster
  6. Mark setup complete
"""

import sys
import urllib3
from pathlib import Path

import requests
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HAL_JSON = "application/vnd.netapp.v1.hal+json"
DEFAULT_PASSWORD = "admin"


def load_config() -> dict:
    """Load package variables from environment or infrafoundry.yml.

    Prefers INFRAFOUNDRY_PACKAGE_VARS env var (set by ScriptHandler)
    and falls back to reading infrafoundry.yml for standalone usage.
    """
    import json
    import os

    env_vars = os.environ.get("INFRAFOUNDRY_PACKAGE_VARS")
    if env_vars:
        return json.loads(env_vars)

    # Fallback: read from infrafoundry.yml
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir.parent / "infrafoundry.yml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return data.get("variables", {})


def save_option(base_url: str, name: str, value: str | int | bool, auth: tuple) -> bool:
    """Save a single option via the management-server admin API."""
    r = requests.post(
        f"{base_url}/api/management-server/admin/options",
        json={"options": [{"name": name, "value": value}]},
        headers={"Content-Type": HAL_JSON},
        auth=auth,
        verify=False,
    )
    if r.status_code in (200, 201, 204):
        return True
    # Avoid logging response body — may contain sensitive data
    print(f"    Failed to set {name}: {r.status_code}")
    return False


def main() -> int:
    config = load_config()
    base_url = f"https://{config['ip_address']}"
    new_password = config["aiqum_admin_password"]
    user = config["aiqum_admin_user"]

    print("=== AIQUM Initial Setup (First Experience Wizard) ===")
    print(f"  Target: {base_url}")

    # Determine current password
    auth = (user, DEFAULT_PASSWORD)
    r = requests.get(
        f"{base_url}/api/management-server/admin/options",
        params={"option": "autosupport.enabled"},
        auth=auth,
        verify=False,
    )
    if r.status_code == 401:
        auth = (user, new_password)
        r = requests.get(
            f"{base_url}/api/management-server/admin/options",
            params={"option": "autosupport.enabled"},
            auth=auth,
            verify=False,
        )
        if r.status_code == 401:
            print("  ERROR: Cannot authenticate with default or configured password")
            return 1
        print("  Authenticated with configured password (setup may be partial)")
        password_already_changed = True
    else:
        print("  Authenticated with default password")
        password_already_changed = False

    # Step 1: Email/SMTP
    print("\nStep 1: Configuring email and SMTP...")
    smtp_options = {
        "email.fromAddress": config["aiqum_admin_email"],
        "mail.smtp.host": config["smtp_server"],
        "mail.smtp.port": config["smtp_port"],
        "mail.smtp.starttls": "true",
        "mail.smtp.username": config["smtp_user"],
        "mail.smtp.password": config["smtp_password"],
    }
    all_ok = True
    for name, value in smtp_options.items():
        if not save_option(base_url, name, value, auth):
            all_ok = False
    print(f"  Email/SMTP: {'OK' if all_ok else 'PARTIAL (check above)'}")

    # Step 2: AutoSupport
    print("\nStep 2: Enabling AutoSupport...")
    if save_option(base_url, "autosupport.enabled", "true", auth):
        print("  AutoSupport: OK")
    else:
        print("  AutoSupport: FAILED")
        return 1

    # Step 3: Change password
    print("\nStep 3: Changing admin password...")
    if password_already_changed:
        print("  Skipped (already using configured password)")
    else:
        r = requests.put(
            f"{base_url}/api/management-server/admin/users/current/password",
            json={
                "currentPassword": DEFAULT_PASSWORD,
                "newPassword": new_password,
                "confirmPassword": new_password,
            },
            headers={"Content-Type": HAL_JSON},
            auth=auth,
            verify=False,
        )
        if r.status_code in (200, 201, 204):
            print("  Password: OK")
            auth = (user, new_password)
        else:
            print(f"  Password: FAILED ({r.status_code}) {r.text[:200]}")
            return 1

    # Step 4: API Gateway
    print("\nStep 4: Enabling API Gateway...")
    if save_option(base_url, "api.gateway.enabled", "true", auth):
        print("  API Gateway: OK")
    else:
        print("  API Gateway: FAILED")
        return 1

    # Step 5: Add ONTAP cluster
    print(f"\nStep 5: Adding ONTAP cluster ({config['ontap_cluster_ip']})...")
    r = requests.post(
        f"{base_url}/api/admin/datasources/clusters",
        json={
            "address": config["ontap_cluster_ip"],
            "username": config["ontap_admin_user"],
            "password": config["ontap_admin_password"],
            "port": 443,
            "protocol": "https",
        },
        headers={"Content-Type": "application/json"},
        auth=auth,
        verify=False,
    )
    if r.status_code in (200, 201):
        print("  Cluster: OK")
    elif r.status_code == 409:
        print("  Cluster: Already exists (OK)")
    else:
        print(f"  Cluster: {r.status_code} (non-fatal)")
        try:
            print(f"    {r.json().get('error', {}).get('message', r.text[:200])}")
        except Exception:
            print(f"    {r.text[:200]}")

    # Step 6: Mark setup complete
    print("\nStep 6: Marking initial setup complete...")
    if save_option(base_url, "initialSetupComplete", True, auth):
        print("  Setup complete: OK")
    else:
        print("  Setup complete: FAILED")
        return 1

    print(f"\n=== AIQUM Initial Setup Complete ===")
    print(f"  URL: {base_url}/")
    print(f"  User: {user}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
