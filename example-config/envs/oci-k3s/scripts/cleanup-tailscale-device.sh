#!/bin/bash
# cleanup-tailscale-device.sh
#
# Remove a single Tailscale device when destroying an instance.
# This script is called as a resource-level hook with INFRAFOUNDRY_RESOURCE
# set to the instance name.
#
# Required environment variables:
#   TAILSCALE_API_KEY - Tailscale API access token
#   INFRAFOUNDRY_RESOURCE - Instance name (set automatically)
#
# See: https://tailscale.com/kb/1101/api/

set -euo pipefail

# Validate required variables
if [ -z "${TAILSCALE_API_KEY:-}" ]; then
    echo "ERROR: TAILSCALE_API_KEY not set"
    exit 1
fi

if [ -z "${INFRAFOUNDRY_RESOURCE:-}" ]; then
    echo "ERROR: INFRAFOUNDRY_RESOURCE not set (this should be set automatically)"
    exit 1
fi

DEVICE_NAME="$INFRAFOUNDRY_RESOURCE"
echo "Looking up Tailscale device: $DEVICE_NAME"

# Get device ID from Tailscale API
DEVICE_ID=$(curl -s \
    -H "Authorization: Bearer $TAILSCALE_API_KEY" \
    "https://api.tailscale.com/api/v2/tailnet/-/devices" | \
    jq -r ".devices[] | select(.hostname == \"$DEVICE_NAME\") | .id" | head -1)

if [ -z "$DEVICE_ID" ] || [ "$DEVICE_ID" = "null" ]; then
    echo "Device '$DEVICE_NAME' not found in Tailscale - may already be removed"
    exit 0
fi

echo "Found device ID: $DEVICE_ID"
echo "Removing device from Tailscale..."

# Delete the device
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X DELETE \
    -H "Authorization: Bearer $TAILSCALE_API_KEY" \
    "https://api.tailscale.com/api/v2/device/$DEVICE_ID")

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
    echo "Successfully removed $DEVICE_NAME from Tailscale"
else
    echo "Warning: Unexpected response code $HTTP_CODE when removing device"
    # Don't fail - the device might already be gone
fi
