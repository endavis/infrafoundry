#!/bin/bash
# ONTAP Cluster — Pre-Destroy Deregistration Event Handler (#1646)
#
# Triggered by the blueprint's on_destroying event, after the destroy is confirmed
# and before any terraform destroy, while the cluster is still up. Removes the
# cluster from the NetApp Console, then from AIQUM, and waits for AIQUM to finish
# the deletion (AIQUM needs the cluster reachable to complete it). Each step skips
# when its inputs (console_* / aiqum_*) are not set.
#
# on_destroy (ontap-destroy-cleanup.sh) remains as the fallback for a cluster that
# was already down; it finds nothing when this script succeeded.
#
# Both removals always run; the script exits non-zero if either failed. The
# blueprint sets continue_on_error, so a failure is reported without blocking the
# destroy.
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

if ! python3 "${BLUEPRINT_DIR}/scripts/ontap-aiqum-register.py" --remove --wait; then
    echo "WARNING: could not remove the cluster from AIQUM; delete the data source by hand" >&2
    status=1
fi

exit "$status"
