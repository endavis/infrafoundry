#!/bin/bash
# k3s node kubeconfig mode — after_apply handler (Proxmox variant)
#
# Pipes k3s-kubeconfig-mode-node.sh to the k3s server as root, so a cluster
# installed with a readable node kubeconfig becomes owner-only. It restarts
# nothing and is idempotent, so it is safe on a running cluster.
#
# Workflow after_apply handlers get no package variables, so the blueprint
# passes everything through its env: block:
#   K3S_SERVER_IP, K3S_SERVER_NAME, K3S_JUMPHOST (empty = ssh directly),
#   K3S_KNOWN_HOSTS (the pinned SSH host keys, ";"-separated known_hosts lines)
#
# The handler has continue_on_error, so a failure is appended to
# INFRAFOUNDRY_WARNINGS_FILE and the step is retried on the next apply.

set -euo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

SERVER_IP="${K3S_SERVER_IP:-}"
if [ -z "${SERVER_IP}" ]; then
    echo "ERROR: K3S_SERVER_IP is not set" >&2
    exit 1
fi
SERVER_NAME="${K3S_SERVER_NAME:-${SERVER_IP}}"
JUMPHOST="${K3S_JUMPHOST:-}"

# These values are spliced into ssh command strings; restrict their characters.
if ! [[ "${SERVER_IP}" =~ ^[A-Za-z0-9.:-]+$ ]]; then
    echo "ERROR: invalid K3S_SERVER_IP '${SERVER_IP}'" >&2
    exit 1
fi
if [ -n "${JUMPHOST}" ] && ! [[ "${JUMPHOST}" =~ ^[A-Za-z0-9._@:-]+$ ]]; then
    echo "ERROR: invalid K3S_JUMPHOST '${JUMPHOST}'" >&2
    exit 1
fi

# shellcheck source=k3s-lib.sh
source "${BLUEPRINT_DIR}/scripts/proxmox/k3s-lib.sh"
trap 'k3s_ssh_cleanup' EXIT

warn() {
    if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
        printf '{"source": "k3s-kubeconfig-mode", "message": "%s"}\n' "$1" >> "${INFRAFOUNDRY_WARNINGS_FILE}"
    fi
}

echo "=== k3s node kubeconfig mode ==="
echo "Server: ${SERVER_NAME} (${SERVER_IP})"
echo "Jumphost: ${JUMPHOST:-<direct>}"

rc=0
remote_root_cmd "${SERVER_IP}" "bash -s" < "${BLUEPRINT_DIR}/scripts/proxmox/k3s-kubeconfig-mode-node.sh" || rc=$?
if [ "${rc}" -ne 0 ]; then
    warn "k3s node kubeconfig mode step failed (exit ${rc}); it is retried on the next apply"
    exit "${rc}"
fi
echo "=== k3s node kubeconfig mode done ==="
