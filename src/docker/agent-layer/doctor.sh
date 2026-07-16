#!/usr/bin/env sh
set -eu

AGENT_TYPE="${PAYSKILLS_AGENT_TYPE:-all}"

case "$AGENT_TYPE" in
    claude-code)
        REQUIRED_COMMANDS="node npm python3 git claude"
        ;;
    openclaw)
        REQUIRED_COMMANDS="node npm python3 git openclaw"
        ;;
    hermes)
        REQUIRED_COMMANDS="python3 git hermes"
        ;;
    all)
        REQUIRED_COMMANDS="node npm python3 git claude openclaw hermes"
        ;;
    *)
        printf 'unsupported PAYSKILLS_AGENT_TYPE: %s\n' "$AGENT_TYPE" >&2
        exit 22
        ;;
esac

missing=0
for cmd in $REQUIRED_COMMANDS; do
    if command -v "$cmd" >/dev/null 2>&1; then
        printf '%s: %s\n' "$cmd" "$(command -v "$cmd")"
    else
        printf '%s: missing\n' "$cmd" >&2
        missing=1
    fi
done

exit "$missing"
