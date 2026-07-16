#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${APP_PORT:-8131}"
export APP_PORT
export APP_BASE_URL="${APP_BASE_URL:-http://localhost:${APP_PORT}}"

docker compose up --build -d

for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${APP_PORT}/health.php" >/dev/null; then
    echo "edoc-h5 is ready at http://localhost:${APP_PORT}"
    exit 0
  fi
  sleep 2
done

docker compose logs --tail=120
exit 1
