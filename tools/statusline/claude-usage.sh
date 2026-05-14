#!/bin/bash

# Opt-in Claude Max usage helper for statusline display.
# Outputs: 5h:N% 7d:N% on success, or literal ? on any failure.
# Wire into .claude/statusline-command.sh manually — not called by default.
#
# Requirements: curl, jq, active Claude Code OAuth login
# See: docs/development/ai/statusline.md#opt-in-claude-max-usage-display

# Cache TTL in seconds
MAX_AGE=60

CREDS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CREDS_FILE="$CREDS_DIR/.credentials.json"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/claude-usage.json"

# Check cache freshness first — avoids a network call and a token read on every invocation
if [[ -f "$CACHE" ]]; then
    if stat -f %m "$CACHE" >/dev/null 2>&1; then
        cache_mtime=$(stat -f %m "$CACHE" 2>/dev/null)
    else
        cache_mtime=$(stat -c %Y "$CACHE" 2>/dev/null)
    fi
    if [[ -n "$cache_mtime" ]] && [[ "$cache_mtime" =~ ^[0-9]+$ ]]; then
        now=$(date +%s)
        age=$((now - cache_mtime))
        if [[ $age -lt $MAX_AGE ]]; then
            # Try to parse the cached response
            result=$(jq -r '"5h:\(.five_hour.utilization|floor)% 7d:\(.seven_day.utilization|floor)%"' "$CACHE" 2>/dev/null)
            if [[ -n "$result" ]]; then
                echo "$result"
                exit 0
            fi
            # Cache parse failed — fall through to emit ? (no network attempt without a token)
            echo "?"
            exit 0
        fi
    fi
fi

# Read OAuth token from credentials
token=$(jq -r '.claudeAiOauth.accessToken // empty' "$CREDS_FILE" 2>/dev/null)
if [[ -z "$token" ]]; then
    echo "?"
    exit 0
fi

# Fetch fresh data
response=$(curl -sf --max-time 5 \
    -H "Authorization: Bearer $token" \
    -H "anthropic-beta: oauth-2025-04-20" \
    "https://api.anthropic.com/api/oauth/usage" 2>/dev/null)
if [[ -z "$response" ]]; then
    echo "?"
    exit 0
fi

# Save to cache and parse
echo "$response" > "$CACHE" 2>/dev/null
result=$(jq -r '"5h:\(.five_hour.utilization|floor)% 7d:\(.seven_day.utilization|floor)%"' "$CACHE" 2>/dev/null)
if [[ -n "$result" ]]; then
    echo "$result"
else
    echo "?"
fi
