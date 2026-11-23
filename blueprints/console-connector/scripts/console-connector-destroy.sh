#!/bin/bash
# Console Connector — Destroy Event Handler (#1629)
#
# Triggered by the blueprint's on_destroy event. Runs after the VM is destroyed and
# removes every agent registered at the package's ip_address from the NetApp Console.
# Skips (exit 0) when the service account inputs are not set. No secret is put on argv.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_PACKAGE_VARS  - required: JSON string of all package variables

set -uo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
: "${INFRAFOUNDRY_PACKAGE_VARS:?required: run via foundry, not directly}"

if ! python3 "${BLUEPRINT_DIR}/scripts/console-connector-register.py" --remove; then
    echo "ERROR: could not remove the agent from the NetApp Console; remove it under Agents > Manage agents" >&2
    exit 1
fi
