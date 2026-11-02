#!/bin/bash
# ONTAP Cluster — Destroy Cleanup Event Handler (#1225)
#
# Triggered by the blueprint's on_destroy event. Removes the cluster from the
# NetApp Console and from AIQUM so a rebuild registers the new cluster. Each
# step skips when its inputs (console_* / aiqum_*) are not set.
#
# Both removals always run; the script exits non-zero if either failed. The
# blueprint sets continue_on_error, so a failure is reported without failing
# the destroy (the VMs are already gone).
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_PACKAGE_VARS  - required: JSON string of all package variables

set -uo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
: "${INFRAFOUNDRY_PACKAGE_VARS:?required: run via foundry, not directly}"

status=0

if ! python3 "${BLUEPRINT_DIR}/scripts/ontap-console-discover.py" --remove; then
    echo "WARNING: could not remove the cluster from the NetApp Console; delete it by hand" >&2
    status=1
fi

if ! python3 "${BLUEPRINT_DIR}/scripts/ontap-aiqum-register.py" --remove; then
    echo "WARNING: could not remove the cluster from AIQUM; delete the data source by hand" >&2
    status=1
fi

exit "$status"
