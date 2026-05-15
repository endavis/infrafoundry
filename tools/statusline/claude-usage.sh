#!/bin/bash

# Opt-in Claude Max usage helper for statusline display.
# Outputs: 5h:N%@HHMM wk:N%@aaa-HHMM on success, or literal ? on any failure.
# Wire into .claude/statusline-command.sh manually — not called by default.
#
# Requirements: curl, jq, python3, active Claude Code OAuth login
# See: docs/development/ai/statusline.md#opt-in-claude-max-usage-display

# Cache TTL in seconds
MAX_AGE=60

CREDS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CREDS_FILE="$CREDS_DIR/.credentials.json"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/claude-usage.json"

# Format a single ISO timestamp into local-timezone compact time.
# Usage: _fmt_ts <iso_string> <strftime_format>
# Returns empty string on failure.
_fmt_ts() {
    local iso="$1"
    local fmt="$2"
    python3 -c "
from datetime import datetime
import sys
try:
    dt = datetime.fromisoformat(sys.argv[1]).astimezone()
    print(dt.strftime(sys.argv[2]))
except Exception:
    sys.exit(1)
" "$iso" "$fmt" 2>/dev/null
}

# Parse a usage JSON file and emit the formatted statusline segment.
# Usage: parse_usage <json_file>
# On success: prints  5h:N%@HHMM wk:N%@aaa-HHMM  and returns 0.
# On any failure: prints ? and returns 1.
parse_usage() {
    local file="$1"
    # Extract the four fields as tab-separated; 'empty' if any field is missing.
    local record
    record=$(jq -r '
        if (.five_hour.utilization != null) and (.five_hour.resets_at != null) and
           (.seven_day.utilization != null) and (.seven_day.resets_at != null)
        then [
            (.five_hour.utilization | floor | tostring),
            .five_hour.resets_at,
            (.seven_day.utilization | floor | tostring),
            .seven_day.resets_at
        ] | join("\t")
        else empty
        end
    ' "$file" 2>/dev/null)

    if [[ -z "$record" ]]; then
        echo "?"
        return 1
    fi

    IFS=$'\t' read -r fh_pct fh_ts wk_pct wk_ts <<< "$record"

    local fh_time wk_time
    fh_time=$(_fmt_ts "$fh_ts" "%H%M")
    if [[ -z "$fh_time" ]]; then
        echo "?"
        return 1
    fi

    wk_time=$(_fmt_ts "$wk_ts" "%a-%H%M")
    if [[ -z "$wk_time" ]]; then
        echo "?"
        return 1
    fi

    echo "5h:${fh_pct}%@${fh_time} wk:${wk_pct}%@${wk_time}"
    return 0
}

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
            parse_usage "$CACHE"
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
parse_usage "$CACHE"
