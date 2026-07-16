#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${PAYSKILLS_CONFIG:-$ROOT/config/config.yaml}"
declare -a RUN_ARGS=()
RUN_ARGS_COUNT=0
INIT=0

load_local_env() {
    local env_file="$ROOT/config/.env"
    if [[ -f "$env_file" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$env_file"
        set +a
    fi
}

init_package() {
    local env_file="$ROOT/config/.env"
    echo "Initialized PaySkills exported benchmark suite"
    echo "config: $CONFIG"
    if [[ -f "$env_file" ]]; then
        echo "exists: $env_file (not overwritten)"
    else
        cp "$ROOT/config/.env.example" "$env_file"
        chmod 0600 "$env_file" 2>/dev/null || true
        echo "created: $env_file"
    fi
    cat <<'EOF'
next:
- edit config/config.yaml
- fill config/.env if agent.api_key_env or judge.api_key_env is configured
- run ./run.sh --doctor
- run ./run.sh
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            RUN_ARGS+=("$1")
            RUN_ARGS_COUNT=$((RUN_ARGS_COUNT + 1))
            ;;
        --init)
            INIT=1
            ;;
        --config)
            if [[ $# -lt 2 ]]; then
                echo "ERROR --config requires a file path" >&2
                exit 2
            fi
            CONFIG="$2"
            shift
            ;;
        --config=*)
            CONFIG="${1#--config=}"
            ;;
        *)
            RUN_ARGS+=("$1")
            RUN_ARGS_COUNT=$((RUN_ARGS_COUNT + 1))
            ;;
    esac
    shift
done

if [[ "$RUN_ARGS_COUNT" -gt 0 ]]; then
    for arg in "${RUN_ARGS[@]}"; do
        if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
            cat <<'EOF'
usage: ./run.sh [--config FILE] [--init] [--doctor] [--dry-run]

Run this exported PaySkills benchmark suite.

options:
  --config FILE  use a config file other than ./config/config.yaml
  --init     create config/.env from config/.env.example without overwriting existing secrets
  --doctor   check package layout, config, selected task instances, and runtime readiness
  --dry-run  list selected task instances and helper requirements without running them
  -h, --help show this help message

configuration:
  Edit config/config.yaml, pass --config FILE, or set PAYSKILLS_CONFIG=/path/to/config.yaml.
  For local secrets, run: ./run.sh --init
  config/.env is loaded automatically by ./run.sh and is ignored by git.
EOF
            exit 0
        fi
    done
fi

if [[ "$INIT" -eq 1 ]]; then
    if [[ "$RUN_ARGS_COUNT" -gt 0 ]]; then
        echo "ERROR --init cannot be combined with run, doctor, dry-run, or unknown arguments" >&2
        exit 2
    fi
    init_package
    exit 0
fi

load_local_env

if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR config file not found: $CONFIG" >&2
    echo "Edit $ROOT/config/config.yaml, pass --config FILE, or set PAYSKILLS_CONFIG to another config file." >&2
    exit 2
fi

if [[ "$RUN_ARGS_COUNT" -gt 0 ]]; then
    exec "$ROOT/src/bin/payskills-run" \
        --export-root "$ROOT" \
        --config "$CONFIG" \
        "${RUN_ARGS[@]}"
else
    exec "$ROOT/src/bin/payskills-run" \
        --export-root "$ROOT" \
        --config "$CONFIG"
fi
