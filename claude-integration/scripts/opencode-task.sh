#!/usr/bin/env bash
# Execute a coding task via opencode serve REST API.
# Usage: opencode-task.sh <repo_root> <prompt> [timeout]
# Output: JSON result on stdout

set -euo pipefail

REPO_ROOT="${1:?Usage: opencode-task.sh <repo_root> <prompt> [timeout]}"
PROMPT="${2:?Missing prompt}"
TIMEOUT="${3:-300}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure server is running
PORT=$("$SCRIPT_DIR/opencode-ensure.sh" "$REPO_ROOT")
BASE="http://127.0.0.1:${PORT}"

# Create session
SESSION_ID=$(curl -sf -X POST "$BASE/session" -H 'Content-Type: application/json' -d '{}' | jq -r '.id')
if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
    echo '{"success":false,"error":"Failed to create session"}'
    exit 1
fi

# Send prompt (fire-and-forget)
HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' -X POST \
    "$BASE/session/${SESSION_ID}/prompt_async" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg p "$PROMPT" '{parts:[{type:"text",text:$p}]}')")

if [ "$HTTP_CODE" != "204" ] && [ "$HTTP_CODE" != "200" ]; then
    echo "{\"success\":false,\"error\":\"prompt_async returned $HTTP_CODE\"}"
    exit 1
fi

# Monitor SSE for completion
timeout "$TIMEOUT" curl -sfN "$BASE/event" | while IFS= read -r line; do
    case "$line" in
        data:*)
            json="${line#data: }"
            etype=$(echo "$json" | jq -r '.type // empty' 2>/dev/null) || continue
            sid=$(echo "$json" | jq -r '.properties.sessionID // empty' 2>/dev/null) || true

            case "$etype" in
                file.edited)
                    file=$(echo "$json" | jq -r '.properties.file // empty' 2>/dev/null) || true
                    [ -n "$file" ] && echo "FILE:$file"
                    ;;
                session.idle)
                    [ "$sid" = "$SESSION_ID" ] && echo "DONE" && break
                    ;;
                session.status)
                    status=$(echo "$json" | jq -r '.properties.status.type // empty' 2>/dev/null) || true
                    [ "$status" = "idle" ] && [ "$sid" = "$SESSION_ID" ] && echo "DONE" && break
                    ;;
            esac
            ;;
    esac
done > /tmp/ninja-sse-$$.log

# Parse results
FILES=$(grep "^FILE:" /tmp/ninja-sse-$$.log 2>/dev/null | sed 's/^FILE://' | jq -R . | jq -s .)
GOT_DONE=$(grep -c "^DONE" /tmp/ninja-sse-$$.log 2>/dev/null || echo "0")
rm -f /tmp/ninja-sse-$$.log

if [ "$GOT_DONE" -gt 0 ]; then
    jq -n --argjson files "${FILES:-[]}" --arg sid "$SESSION_ID" \
        '{success:true, files_changed:$files, session_id:$sid}'
else
    jq -n --arg sid "$SESSION_ID" \
        '{success:false, error:"timeout waiting for completion", session_id:$sid}'
fi
