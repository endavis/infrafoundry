#!/bin/bash
# Shared helper: re-execute the calling script on the jumphost if one is
# configured in the package variables. Sourced by blueprint post-terraform
# scripts that need to run one hop from the VM (e.g. to reach API endpoints
# on a VLAN that isn't directly routable from the operator's workstation).
#
# Usage (at the top of any blueprint script):
#
#   #!/bin/bash
#   set -euo pipefail
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "${SCRIPT_DIR}/../../_lib/reexec-on-jumphost.sh"
#
#   # ... rest of the blueprint's script, unchanged ...
#
# Behavior:
#   - If no jumphost is configured, returns immediately. Script continues
#     running on the operator's host.
#   - If a jumphost is configured and we are NOT already on it:
#       * rsyncs the calling script's directory to the jumphost
#       * re-executes the same script there via ssh
#       * pipes INFRAFOUNDRY_PACKAGE_VARS through stdin (secrets never appear
#         on the command line or in ps output)
#       * exits with the remote exit code
#   - Strips "jumphost" from the forwarded INFRAFOUNDRY_PACKAGE_VARS so the
#     downstream copy of the script parses the JSON and sees no jumphost,
#     and its existing remote_cmd helpers (which branch on ${jumphost:-}) do
#     direct SSH to the target VM rather than nested jumphost-to-jumphost.
#   - INFRAFOUNDRY_ON_JUMPHOST=1 is set on re-exec as a recursion guard.
#
# Prerequisites on the jumphost:
#   - bash, rsync, python3 (standard on any ansible control node)
#   - Whatever the downstream script itself needs (e.g. python3 requests)

if [ -n "${INFRAFOUNDRY_VAR_jumphost:-}" ] && [ -z "${INFRAFOUNDRY_ON_JUMPHOST:-}" ]; then
    _JH="${INFRAFOUNDRY_VAR_jumphost}"
    _CALLER="$(realpath "$0")"
    _CALLER_DIR="$(dirname "${_CALLER}")"
    _CALLER_NAME="$(basename "${_CALLER}")"
    _REMOTE_DIR="/tmp/infrafoundry-$$"

    _REMOTE_VARS=$(python3 -c '
import json, os, sys
v = json.loads(os.environ.get("INFRAFOUNDRY_PACKAGE_VARS", "{}"))
v.pop("jumphost", None)
sys.stdout.write(json.dumps(v))
')

    echo "[$(date +%H:%M:%S)] reexec: shipping ${_CALLER_DIR} to ${_JH} and running ${_CALLER_NAME}"
    ssh -o StrictHostKeyChecking=no "${_JH}" "mkdir -p ${_REMOTE_DIR}" || exit 1
    rsync -a -e "ssh -o StrictHostKeyChecking=no" "${_CALLER_DIR}/" "${_JH}:${_REMOTE_DIR}/" || exit 1
    printf '%s' "${_REMOTE_VARS}" | ssh -o StrictHostKeyChecking=no "${_JH}" \
        "INFRAFOUNDRY_ON_JUMPHOST=1 INFRAFOUNDRY_PACKAGE_VARS=\"\$(cat)\" bash ${_REMOTE_DIR}/${_CALLER_NAME}"
    _rc=$?
    ssh -o StrictHostKeyChecking=no "${_JH}" "rm -rf ${_REMOTE_DIR}" 2>/dev/null || true
    exit ${_rc}
fi
