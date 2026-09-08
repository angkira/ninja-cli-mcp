#!/bin/sh
set -eu

: "${NINJA_HEALTHCHECK_PORT:?NINJA_HEALTHCHECK_PORT must be set}"
NINJA_HEALTHCHECK_PATH="${NINJA_HEALTHCHECK_PATH:-/sse}"

python - "$NINJA_HEALTHCHECK_PORT" "$NINJA_HEALTHCHECK_PATH" <<'PY'
import sys
import urllib.error
import urllib.request

port, path = sys.argv[1:]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
        if response.status < 200 or response.status >= 500:
            raise SystemExit(1)
except (OSError, urllib.error.URLError, TimeoutError):
    raise SystemExit(1)
PY
