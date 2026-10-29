#!/bin/bash
# NetApp Console agent Post-Terraform Setup
#
# Installs Docker Engine and the NetApp Console agent on the Ubuntu 24.04 VM,
# then waits for the agent web page. Registration with the NetApp Console is
# scripted (Phase 5) when console_client_id, console_client_secret and
# console_admin_email are set; otherwise it is a manual browser step (see the
# blueprint README).
#
# All remote commands run through the jumphost when `jumphost` is set, since the
# SSH key for the VM may only exist there.
#
# Package variables are injected by InfraFoundry as:
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
#   INFRAFOUNDRY_PACKAGE_VARS  - JSON string of all package variables
#
# Prerequisites:
# - Ubuntu 24.04 VM created and booted with cloud-init
# - Console agent installer mirrored at console_agent_url_base
set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

# SCRIPT_DIR points at this blueprint's scripts/ dir (sibling remote script).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# PACKAGE_DIR must come from the framework, not from $(dirname "$0").
PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"
export PACKAGE_DIR

if [ -z "${INFRAFOUNDRY_PACKAGE_VARS:-}" ]; then
    echo "ERROR: INFRAFOUNDRY_PACKAGE_VARS is not set — run via 'foundry infra apply', not directly" >&2
    exit 1
fi
# Scalar package variables become shell variables (values shell-quoted).
eval "$(python3 -c "
import json, os, shlex
v = json.loads(os.environ['INFRAFOUNDRY_PACKAGE_VARS'])
for k, val in v.items():
    if isinstance(val, (str, int, float, bool)) and k.isidentifier():
        print(f'{k}={shlex.quote(str(val))}')
")"

JUMPHOST="${jumphost:-}"
# Host keys are not checked for the VM: it gets new keys on every rebuild. The
# jumphost is a long-lived host, so its connection keeps normal verification.
VM_SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
SSH="ssh ${VM_SSH_OPTS} -o ConnectTimeout=10"
JUMP_SSH="ssh -o ConnectTimeout=10"
SSH_USER="${ssh_user:-ansible}"
DOCKER_VERSION="${docker_version:-27.5.1}"
INSTALL_ARGS="${console_agent_install_args:-}"
: "${console_agent_url_base:?required: set console_agent_url_base in the package}"
: "${console_agent_installer:?required: set console_agent_installer in the package}"
: "${console_agent_sha256:?required: set console_agent_sha256 in the package}"

if [ -n "${JUMPHOST}" ]; then
    remote_cmd() { ${JUMP_SSH} ${JUMPHOST} "${SSH} ${SSH_USER}@${1} '${2}'"; }
    remote_cmd_long() { ${JUMP_SSH} -o ServerAliveInterval=30 ${JUMPHOST} "${SSH} -o ServerAliveInterval=30 ${SSH_USER}@${1} '${2}'"; }
    # Stage through a private mktemp file on the jumphost, removed afterwards.
    remote_upload() {
        local staged
        staged=$(${JUMP_SSH} ${JUMPHOST} mktemp) || return 1
        scp "$1" "${JUMPHOST}:${staged}" \
            && ${JUMP_SSH} ${JUMPHOST} "scp ${VM_SSH_OPTS} ${staged} ${SSH_USER}@${2}:${3}; rc=\$?; rm -f ${staged}; exit \$rc"
    }
else
    remote_cmd() { ${SSH} ${SSH_USER}@${1} "${2}"; }
    remote_cmd_long() { ${SSH} -o ServerAliveInterval=30 ${SSH_USER}@${1} "${2}"; }
    remote_upload() { scp ${VM_SSH_OPTS} "$1" "${SSH_USER}@${2}:${3}"; }
fi

log "=== NetApp Console agent Post-Terraform Setup ==="
echo "VM: ${vm_name} (${ip_address})"
if [ -n "${JUMPHOST}" ]; then
    echo "Jumphost: ${JUMPHOST}"
else
    echo "Jumphost: (direct SSH)"
fi

# --- Phase 0: Preflight ---
echo ""
log "--- Phase 0: Preflight checks ---"
if ! ssh-add -l >/dev/null 2>&1; then
    rc=$?
    if [ $rc -eq 1 ]; then
        echo "ERROR: ssh-agent on $(hostname) has no keys loaded" >&2
        echo "       Load your key (e.g. 'ssh-add ~/.ssh/id_ed25519') and re-apply" >&2
    else
        echo "ERROR: cannot reach ssh-agent on $(hostname) (rc=$rc, SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-unset})" >&2
    fi
    exit 1
fi
echo "  ssh-agent: $(ssh-add -l | wc -l) key(s) loaded"

# No one-shot SSH probe here: the VM may still be booting. Phase 1 retries and
# prints the last SSH error if it never becomes reachable.
WAIT_ERR=$(mktemp)
CURL_ERR=$(mktemp)
trap 'rm -f "$WAIT_ERR" "$CURL_ERR"' EXIT

# --- Phase 1: Wait for SSH, then cloud-init ---
echo ""
log "--- Phase 1: Waiting for VM to be reachable ---"
MAX_WAIT=300
ELAPSED=0
while ! remote_cmd "${ip_address}" "echo ready" >"$WAIT_ERR" 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: VM not reachable after ${MAX_WAIT}s" >&2
        sed 's/^/    /' "$WAIT_ERR" >&2
        exit 1
    fi
    echo "  Waiting for SSH... (${ELAPSED}s)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
echo "  VM is reachable via SSH"
echo "  Waiting for cloud-init to finish..."
remote_cmd_long "${ip_address}" "sudo cloud-init status --wait >/dev/null 2>&1 || true"

# --- Phase 2: Upload the remote install script ---
echo ""
log "--- Phase 2: Uploading install script ---"
REMOTE_SCRIPT="${SCRIPT_DIR}/console-connector-install-remote.sh"
if [ ! -f "${REMOTE_SCRIPT}" ]; then
    echo "ERROR: Install script not found: ${REMOTE_SCRIPT}" >&2
    exit 1
fi
# Into the VM user's home, not a shared /tmp path.
remote_upload "${REMOTE_SCRIPT}" "${ip_address}" "console-connector-install-remote.sh"

# --- Phase 3: Install Docker and the Console agent ---
echo ""
log "--- Phase 3: Installing Docker ${DOCKER_VERSION} and the Console agent ---"
remote_cmd_long "${ip_address}" "DOCKER_VERSION='${DOCKER_VERSION}' CONSOLE_AGENT_URL_BASE='${console_agent_url_base}' CONSOLE_AGENT_INSTALLER='${console_agent_installer}' CONSOLE_AGENT_SHA256='${console_agent_sha256}' CONSOLE_AGENT_INSTALL_ARGS='${INSTALL_ARGS}' bash ~/console-connector-install-remote.sh"

# --- Phase 4: Wait for the agent web page, print manual steps ---
echo ""
log "--- Phase 4: Waiting for the Console agent web page ---"
MAX_WAIT=900
ELAPSED=0
while ! curl -skS -o /dev/null -w "%{http_code}" "https://${ip_address}/" 2>"$CURL_ERR" | grep -q "200\|302\|401"; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: Console agent web page not available after ${MAX_WAIT}s" >&2
        if [ -s "$CURL_ERR" ]; then
            sed 's/^/    /' "$CURL_ERR" >&2
        fi
        exit 1
    fi
    echo "  Waiting for the Console agent... (${ELAPSED}s)"
    sleep 15
    ELAPSED=$((ELAPSED + 15))
done
echo "  Console agent web page is available"

# --- Phase 5: Register the agent with the NetApp Console (optional) ---
echo ""
log "--- Phase 5: Registering the Console agent ---"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required for registration" >&2; exit 1; }
# The helper reads INFRAFOUNDRY_PACKAGE_VARS itself; no secret goes on a command line.
REGISTRATION_REQUESTED=0
if [ -n "${console_client_id:-}${console_client_secret:-}${console_admin_email:-}" ]; then
    REGISTRATION_REQUESTED=1
fi
AGENT_CERT=""
if [ "${REGISTRATION_REQUESTED}" -eq 1 ]; then
    # Pin the agent's own certificate (fetched over the SSH channel to the VM) so the
    # bearer token is only ever sent to this agent. A path, not a secret, goes on argv.
    AGENT_CERT=$(mktemp)
    trap 'rm -f "$WAIT_ERR" "$CURL_ERR" "$AGENT_CERT"' EXIT
    remote_cmd "${ip_address}" "openssl s_client -connect 127.0.0.1:443 -servername localhost </dev/null 2>/dev/null | openssl x509" >"$AGENT_CERT"
fi
python3 "${SCRIPT_DIR}/console-connector-register.py" ${AGENT_CERT:+--agent-cert "$AGENT_CERT"}

echo ""
log "=== Console agent install complete ==="
if [ "${REGISTRATION_REQUESTED}" -eq 0 ]; then
    echo "  Registration is a manual step. In a browser:"
    echo "    1. Open https://${ip_address}"
    echo "    2. Log in and choose your NetApp Console organization"
    echo "    3. Name the system; keep restricted mode disabled"
    echo "    4. Select 'Let's start'"
fi
echo "  Then add the ONTAP cluster in the NetApp Console (see the blueprint README)."
