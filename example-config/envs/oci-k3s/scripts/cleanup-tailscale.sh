#!/bin/bash
# cleanup-tailscale.sh - Remove OCI K3s Tailscale devices before infrastructure destroy
#
# Usage:
#   TAILSCALE_API_KEY=tskey-api-xxx ./cleanup-tailscale.sh
#
# Or with tailnet specified:
#   TAILSCALE_API_KEY=tskey-api-xxx TAILSCALE_TAILNET=example.com ./cleanup-tailscale.sh
#
# Environment Variables:
#   TAILSCALE_API_KEY   - Required. Tailscale API key with devices:write scope
#   TAILSCALE_TAILNET   - Optional. Tailnet name (default: "-" for default tailnet)
#   DRY_RUN             - Optional. Set to "true" to show what would be deleted without deleting

set -euo pipefail

# Configuration
TAILNET="${TAILSCALE_TAILNET:--}"
API_BASE="https://api.tailscale.com/api/v2"
DRY_RUN="${DRY_RUN:-false}"

# Hostname patterns to match (devices created by this environment)
HOSTNAME_PATTERNS=(
    "oci-k3s-control"
    "oci-k3s-worker-0"
    "oci-k3s-worker-1"
    "oci-k3s-operator"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required environment variables
if [[ -z "${TAILSCALE_API_KEY:-}" ]]; then
    log_error "TAILSCALE_API_KEY environment variable is required"
    echo ""
    echo "Get an API key from: https://login.tailscale.com/admin/settings/keys"
    echo "Required scopes: devices:read, devices:write"
    exit 1
fi

# Check for required tools
if ! command -v curl &> /dev/null; then
    log_error "curl is required but not installed"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    log_error "jq is required but not installed"
    exit 1
fi

log_info "Fetching Tailscale devices from tailnet: $TAILNET"

# Fetch all devices
DEVICES_RESPONSE=$(curl -s -X GET \
    -u "${TAILSCALE_API_KEY}:" \
    "${API_BASE}/tailnet/${TAILNET}/devices")

# Check for API errors
if echo "$DEVICES_RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
    ERROR_MSG=$(echo "$DEVICES_RESPONSE" | jq -r '.message // .error')
    log_error "API error: $ERROR_MSG"
    exit 1
fi

# Extract devices array
DEVICES=$(echo "$DEVICES_RESPONSE" | jq -c '.devices // []')
DEVICE_COUNT=$(echo "$DEVICES" | jq 'length')

log_info "Found $DEVICE_COUNT total devices in tailnet"

# Track what we'll delete
DELETED_COUNT=0
FAILED_COUNT=0

# Process each hostname pattern
for PATTERN in "${HOSTNAME_PATTERNS[@]}"; do
    # Find devices matching this pattern (hostname starts with pattern)
    MATCHING=$(echo "$DEVICES" | jq -c --arg p "$PATTERN" '[.[] | select(.hostname | startswith($p))]')
    MATCH_COUNT=$(echo "$MATCHING" | jq 'length')

    if [[ "$MATCH_COUNT" -eq 0 ]]; then
        log_warn "No devices found matching pattern: $PATTERN"
        continue
    fi

    # Process each matching device
    echo "$MATCHING" | jq -c '.[]' | while read -r DEVICE; do
        DEVICE_ID=$(echo "$DEVICE" | jq -r '.id')
        DEVICE_NAME=$(echo "$DEVICE" | jq -r '.hostname // .name')
        DEVICE_IP=$(echo "$DEVICE" | jq -r '.addresses[0] // "no-ip"')
        LAST_SEEN=$(echo "$DEVICE" | jq -r '.lastSeen // "unknown"')

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would delete: $DEVICE_NAME ($DEVICE_IP) - ID: $DEVICE_ID"
        else
            log_info "Deleting device: $DEVICE_NAME ($DEVICE_IP)"

            # Delete the device
            DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
                -u "${TAILSCALE_API_KEY}:" \
                "${API_BASE}/device/${DEVICE_ID}")

            HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)
            BODY=$(echo "$DELETE_RESPONSE" | sed '$d')

            if [[ "$HTTP_CODE" == "200" ]] || [[ "$HTTP_CODE" == "204" ]]; then
                log_info "  Successfully deleted $DEVICE_NAME"
                ((DELETED_COUNT++)) || true
            elif [[ "$HTTP_CODE" == "404" ]]; then
                log_warn "  Device $DEVICE_NAME not found (already deleted?)"
            else
                log_error "  Failed to delete $DEVICE_NAME: HTTP $HTTP_CODE"
                if [[ -n "$BODY" ]]; then
                    echo "    Response: $BODY"
                fi
                ((FAILED_COUNT++)) || true
            fi
        fi
    done
done

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Dry run complete. No devices were deleted."
else
    log_info "Cleanup complete."
    # Note: DELETED_COUNT and FAILED_COUNT are in subshell, so we can't access them here
    # The individual log messages show what happened
fi
