#!/bin/bash
# Reverse proxy config — after_apply handler.
#
# Renders the Caddyfile from the routes, sends it to the proxy VM with the node script and
# lets the node validate it and reload Caddy only when it changed. Runs on every apply, so a
# route change reaches the VM. The handler gets no package variables; the blueprint passes
# RP_VM_NAME, RP_IP, RP_JUMPHOST (empty = ssh directly), RP_SSH_USER, RP_KNOWN_HOSTS (the
# pinned SSH host keys), RP_DOMAIN, RP_CERT_DIR, RP_ROUTES and RP_ALLOWED (JSON) in env.
#
# The handler has continue_on_error, so a failure is appended to INFRAFOUNDRY_WARNINGS_FILE
# and the step is retried on the next apply.

set -euo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

warn() {
    if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
        printf '{"source": "reverse-proxy-config", "message": "%s"}\n' "$1" >> "${INFRAFOUNDRY_WARNINGS_FILE}"
    fi
}

fail() {
    echo "ERROR: $1" >&2
    warn "$1"
    exit 1
}

RP_IP="${RP_IP:-}"
RP_VM_NAME="${RP_VM_NAME:-${RP_IP}}"
RP_JUMPHOST="${RP_JUMPHOST:-}"
RP_SSH_USER="${RP_SSH_USER:-ansible}"
RP_CERT_DIR="${RP_CERT_DIR:-/etc/ssl/infrafoundry}"

# These values are spliced into ssh command strings and the node payload; restrict them.
[[ "${RP_IP}" =~ ^[A-Za-z0-9.:-]+$ ]] || fail "invalid RP_IP"
[[ "${RP_VM_NAME}" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid RP_VM_NAME"
[[ "${RP_SSH_USER}" =~ ^[a-z_][a-z0-9_-]*$ ]] || fail "invalid RP_SSH_USER"
if [ -n "${RP_JUMPHOST}" ] && ! [[ "${RP_JUMPHOST}" =~ ^[A-Za-z0-9._@:-]+$ ]]; then
    fail "invalid RP_JUMPHOST"
fi
[[ "${RP_CERT_DIR}" =~ ^/[A-Za-z0-9._/-]*$ ]] || fail "invalid RP_CERT_DIR"

echo "=== reverse proxy config ==="
echo "Proxy: ${RP_VM_NAME} (${RP_IP})"
echo "Jumphost: ${RP_JUMPHOST:-<direct>}"

CADDYFILE=$(python3 -I "${BLUEPRINT_DIR}/scripts/reverse-proxy-caddyfile.py") \
    || fail "the routes are invalid; see the error above"

# Without a site block there is nothing to serve: only ensure Caddy and the cert directory.
CADDYFILE_B64=""
if printf '%s\n' "${CADDYFILE}" | grep -q '^https://'; then
    CADDYFILE_B64=$(printf '%s\n' "${CADDYFILE}" | base64 | tr -d '\n')
else
    echo "no routes: only Caddy and the certificate directory are ensured"
fi

# shellcheck source=reverse-proxy-lib.sh
source "${BLUEPRINT_DIR}/scripts/reverse-proxy-lib.sh"

WAIT_ERR=$(mktemp)
trap 'rm -f "${WAIT_ERR}"; rp_ssh_cleanup' EXIT
MAX_WAIT=300
ELAPSED=0
while ! remote_cmd "${RP_IP}" "echo ready" >"${WAIT_ERR}" 2>&1; do
    if rp_host_key_error "${WAIT_ERR}"; then
        sed 's/^/    /' "${WAIT_ERR}" >&2
        fail "the pinned SSH host key does not match; run 'foundry secrets host-keys --env <env>'"
    fi
    if [ "${ELAPSED}" -ge "${MAX_WAIT}" ]; then
        sed 's/^/    /' "${WAIT_ERR}" >&2
        fail "the proxy VM is not reachable after ${MAX_WAIT}s; it is retried on the next apply"
    fi
    echo "  Waiting for SSH... (${ELAPSED}s)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
remote_cmd "${RP_IP}" "sudo cloud-init status --wait >/dev/null 2>&1 || true"

rc=0
{
    printf 'RP_CADDYFILE_B64=%s\nRP_CERT_DIR=%s\n' "${CADDYFILE_B64}" "${RP_CERT_DIR}"
    cat "${BLUEPRINT_DIR}/scripts/reverse-proxy-node.sh"
} | remote_root_cmd "${RP_IP}" "bash -s" || rc=$?
if [ "${rc}" -eq 3 ]; then
    warn "certificate files are missing on the proxy; run 'foundry certs issue --env <env>' then apply again"
    exit 3
elif [ "${rc}" -ne 0 ]; then
    warn "reverse proxy config step failed (exit ${rc}); it is retried on the next apply"
    exit "${rc}"
fi
echo "=== reverse proxy config done ==="
