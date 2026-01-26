#!/bin/bash
# cleanup-tailscale-devices.sh
#
# Remove ALL Tailscale devices for this environment before destroy.
# This is an environment-level hook that runs before any resources are destroyed.
#
# Required environment variables:
#   TAILSCALE_API_KEY - Tailscale API access token
#   INFRAFOUNDRY_ENV - Environment name (set automatically)
#
# See: https://tailscale.com/kb/1101/api/

set -euo pipefail

# Validate required variables
if [ -z "${TAILSCALE_API_KEY:-}" ]; then
    echo "ERROR: TAILSCALE_API_KEY not set"
    exit 1
fi

ENV_NAME="${INFRAFOUNDRY_ENV:-unknown}"
echo "Cleaning up Tailscale devices for environment: $ENV_NAME"

# Get all devices from Tailscale
DEVICES=$(curl -s \
    -H "Authorization: Bearer $TAILSCALE_API_KEY" \
    "https://api.tailscale.com/api/v2/tailnet/-/devices")

# Filter devices that match our k3s cluster naming pattern
# Adjust the pattern based on your naming convention
DEVICE_IDS=$(echo "$DEVICES" | jq -r '.devices[] | select(.hostname | test("^k3s-")) | .id')

if [ -z "$DEVICE_IDS" ]; then
    echo "No matching Tailscale devices found for cleanup"
    exit 0
fi

REMOVED=0
FAILED=0

for DEVICE_ID in $DEVICE_IDS; do
    HOSTNAME=$(echo "$DEVICES" | jq -r ".devices[] | select(.id == \"$DEVICE_ID\") | .hostname")
    echo "Removing device: $HOSTNAME ($DEVICE_ID)"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE \
        -H "Authorization: Bearer $TAILSCALE_API_KEY" \
        "https://api.tailscale.com/api/v2/device/$DEVICE_ID")

    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
        echo "  Removed successfully"
        ((REMOVED++))
    else
        echo "  Warning: Unexpected response code $HTTP_CODE"
        ((FAILED++))
    fi
done

echo ""
echo "Cleanup complete: $REMOVED removed, $FAILED failed"

# Only fail if all removals failed
if [ "$REMOVED" -eq 0 ] && [ "$FAILED" -gt 0 ]; then
    exit 1
fi
