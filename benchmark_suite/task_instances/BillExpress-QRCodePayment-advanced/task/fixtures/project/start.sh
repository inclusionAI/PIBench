#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -f .case-runtime/app.env ]; then
  set -a
  # shellcheck disable=SC1091
  source .case-runtime/app.env
  set +a
fi

APP_PORT="${APP_PORT:-8142}"
export APP_PORT
export ADMIN_USERNAME="${ADMIN_USERNAME:-developer}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-developer123}"
export CHOKIDAR_USEPOLLING="${CHOKIDAR_USEPOLLING:-true}"
export CHOKIDAR_INTERVAL="${CHOKIDAR_INTERVAL:-1000}"
export ALIPAY_GATEWAY_URL="${ALIPAY_GATEWAY_URL:-http://127.0.0.1:18080/gateway.do}"
export ALIPAY_APP_ID="${ALIPAY_APP_ID:-mock-app-id}"
export ALIPAY_TIMEOUT_MS="${ALIPAY_TIMEOUT_MS:-5000}"

mkdir -p .case-runtime

if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund > .case-runtime/npm-install.log 2>&1
fi

if [ -f .case-runtime/app.pid ]; then
  old_pid="$(cat .case-runtime/app.pid || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" || true
    sleep 1
  fi
fi

nohup npm run dev > .case-runtime/app.log 2>&1 &
echo "$!" > .case-runtime/app.pid

deadline=$((SECONDS + 90))
until curl -fsS -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; do
  if [ "$SECONDS" -gt "$deadline" ]; then
    echo "Application failed to become ready on port ${APP_PORT}" >&2
    tail -80 .case-runtime/app.log >&2 || true
    exit 1
  fi
  sleep 2
done

echo "APP_READY=http://127.0.0.1:${APP_PORT}"
