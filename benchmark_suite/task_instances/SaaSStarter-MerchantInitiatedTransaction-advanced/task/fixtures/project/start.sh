#!/usr/bin/env bash
set -Eeuo pipefail

APP_PORT="${APP_PORT:-3000}"
DB_PORT="${DB_PORT:-54322}"
RUNTIME_DIR="${RUNTIME_DIR:-.case-runtime}"
LOG_FILE="$RUNTIME_DIR/app.log"
PID_FILE="$RUNTIME_DIR/app.pid"
DB_CONTAINER="${DB_CONTAINER:-next_saas_starter_case_postgres}"
POSTGRES_URL="${POSTGRES_URL:-}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${APP_PORT}}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-sk_test_case_placeholder}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_case_placeholder}"
AUTH_SECRET="${AUTH_SECRET:-case-auth-secret-at-least-32-bytes-long}"
POSTGRES_URL_WAS_SET=0
if [ -n "$POSTGRES_URL" ]; then POSTGRES_URL_WAS_SET=1; fi

mkdir -p "$RUNTIME_DIR"
: > "$LOG_FILE"

cleanup_stale() {
  if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" || true)"
    if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi
}

log() { printf "[start.sh] %s\n" "$*" | tee -a "$LOG_FILE"; }

cleanup_stale

if ! command -v pnpm >/dev/null 2>&1; then
  npm install -g pnpm@9.15.9 >>"$LOG_FILE" 2>&1
fi

PNPM_CMD=(pnpm)
PNPM_VERSION="$(pnpm --version 2>/dev/null || true)"
PNPM_MAJOR="${PNPM_VERSION%%.*}"
if [ -z "$PNPM_MAJOR" ] || [ "$PNPM_MAJOR" -gt 9 ] 2>/dev/null; then
  PNPM_CMD=(npx -y pnpm@9.15.9)
fi
log "using package manager: ${PNPM_CMD[*]}"

start_postgres() {
  if command -v pg_ctlcluster >/dev/null 2>&1; then
    log "starting local postgres service"
    sudo -n pg_ctlcluster 16 main start >>"$LOG_FILE" 2>&1 \
      || sudo -n pg_ctlcluster 15 main start >>"$LOG_FILE" 2>&1 \
      || sudo -n service postgresql start >>"$LOG_FILE" 2>&1 \
      || pg_ctlcluster 16 main start >>"$LOG_FILE" 2>&1 \
      || pg_ctlcluster 15 main start >>"$LOG_FILE" 2>&1 \
      || service postgresql start >>"$LOG_FILE" 2>&1
    sudo -n -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" >>"$LOG_FILE" 2>&1 \
      || su postgres -c "psql -c \"ALTER USER postgres PASSWORD 'postgres';\"" >>"$LOG_FILE" 2>&1 \
      || true
    POSTGRES_URL="${POSTGRES_URL:-postgres://postgres:postgres@127.0.0.1:5432/postgres}"
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    log "starting postgres container on port ${DB_PORT}"
    docker rm -f "$DB_CONTAINER" >>"$LOG_FILE" 2>&1 || true
    docker run -d --name "$DB_CONTAINER" \
      -e POSTGRES_DB=postgres \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -p "127.0.0.1:${DB_PORT}:5432" \
      postgres:16.4-alpine >>"$LOG_FILE" 2>&1
    for i in $(seq 1 60); do
      if docker exec "$DB_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        POSTGRES_URL="${POSTGRES_URL:-postgres://postgres:postgres@127.0.0.1:${DB_PORT}/postgres}"
        return 0
      fi
      sleep 1
    done
    docker logs "$DB_CONTAINER" | tail -80 | tee -a "$LOG_FILE" || true
  fi

  log "postgres did not become ready"
  exit 1
}

start_postgres

reset_database_if_needed() {
  if [ "$POSTGRES_URL_WAS_SET" = "1" ]; then
    return 0
  fi
  local base_url db_name admin_url
  base_url="${POSTGRES_URL%/*}"
  db_name="${DB_NAME:-payskills_saas_${APP_PORT}}"
  db_name="$(printf '%s' "$db_name" | tr -c 'A-Za-z0-9_' '_' | cut -c 1-60)"
  admin_url="${base_url}/postgres"
  log "resetting postgres database ${db_name}"
  if command -v psql >/dev/null 2>&1; then
    PGPASSWORD=postgres psql "$admin_url" -v ON_ERROR_STOP=1 \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db_name}' AND pid <> pg_backend_pid();" \
      -c "DROP DATABASE IF EXISTS \"${db_name}\";" \
      -c "CREATE DATABASE \"${db_name}\";" >>"$LOG_FILE" 2>&1
  elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    docker exec "$DB_CONTAINER" psql -U postgres -v ON_ERROR_STOP=1 \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db_name}' AND pid <> pg_backend_pid();" \
      -c "DROP DATABASE IF EXISTS \"${db_name}\";" \
      -c "CREATE DATABASE \"${db_name}\";" >>"$LOG_FILE" 2>&1
  else
    log "could not reset database: psql unavailable"
    return 1
  fi
  POSTGRES_URL="${base_url}/${db_name}"
}

reset_database_if_needed

cat > .env <<ENV
POSTGRES_URL=${POSTGRES_URL}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
BASE_URL=${BASE_URL}
AUTH_SECRET=${AUTH_SECRET}
SKIP_STRIPE_SEED=true
ALIPAY_CASE_LOCAL_PLANS=true
ALIPAY_MOCK_MODE=${ALIPAY_MOCK_MODE:-true}
ALIPAY_ALLOW_UNSIGNED_NOTIFY=${ALIPAY_ALLOW_UNSIGNED_NOTIFY:-true}
ALIPAY_GATEWAY=${ALIPAY_GATEWAY:-http://127.0.0.1:4100/gateway.do}
ALIPAY_APP_ID=${ALIPAY_APP_ID:-case_mock_app}
ALIPAY_PID=${ALIPAY_PID:-case_mock_pid}
ALIPAY_SIGN_SCENE=${ALIPAY_SIGN_SCENE:-INDUSTRY|DIGITAL_MEDIA}
ENV

log "installing dependencies"
"${PNPM_CMD[@]}" install --frozen-lockfile >>"$LOG_FILE" 2>&1

log "running migrations"
"${PNPM_CMD[@]}" db:migrate >>"$LOG_FILE" 2>&1

log "seeding database"
"${PNPM_CMD[@]}" db:seed >>"$LOG_FILE" 2>&1

log "building app"
"${PNPM_CMD[@]}" build >>"$LOG_FILE" 2>&1

log "starting app on ${BASE_URL}"
HOSTNAME=0.0.0.0 PORT="$APP_PORT" "${PNPM_CMD[@]}" start >>"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for i in $(seq 1 90); do
  if curl -fsS "${BASE_URL}" >/dev/null 2>&1; then
    echo "APP_READY=${BASE_URL}"
    log "app ready at ${BASE_URL}"
    exit 0
  fi
  sleep 1
  if [ "$i" = 90 ]; then
    log "app did not become ready"
    tail -120 "$LOG_FILE"
    exit 1
  fi
done
