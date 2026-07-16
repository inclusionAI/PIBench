#!/usr/bin/env bash
# start_app.sh — bring up MariaDB + the PHP app (the agent's modified workspace)
# inside the single case container, without docker-compose / DinD.
#
# Designed to run as the non-root `agent` user: MariaDB datadir + socket live in
# agent-writable paths and the PHP server listens on a high port.
#
# Exports nothing; writes logs to $OUTPUT_DIR and prints READY/FAILED markers.
set -uo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/output}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace/app}"
APP_PORT="${APP_PORT:-8136}"
DATADIR="${EDOC_DATADIR:-/var/lib/edoc-mysql}"
SOCKET="/var/run/mysqld/mysqld.sock"
DB_LOG="$OUTPUT_DIR/mariadb.log"
PHP_LOG="$OUTPUT_DIR/php_server.log"

mkdir -p "$OUTPUT_DIR"
log() { echo "[start_app] $*"; }

# Make sure the dirs we need are writable even if the image perms drifted.
mkdir -p "$DATADIR" /var/run/mysqld 2>/dev/null || sudo mkdir -p "$DATADIR" /var/run/mysqld
chmod 0777 /var/run/mysqld 2>/dev/null || sudo chmod 0777 /var/run/mysqld 2>/dev/null || true

# --- 1. Initialize + start MariaDB -------------------------------------------
if [ ! -d "$DATADIR/mysql" ]; then
  log "initializing MariaDB datadir at $DATADIR"
  mariadb-install-db --no-defaults --auth-root-authentication-method=normal \
      --datadir="$DATADIR" --user="$(id -un)" >> "$DB_LOG" 2>&1 || {
    log "FAILED: mariadb-install-db"; echo "FAILED"; exit 1; }
fi

log "starting mariadbd"
mariadbd --no-defaults \
    --datadir="$DATADIR" \
    --socket="$SOCKET" \
    --port=3306 \
    --bind-address=127.0.0.1 \
    --pid-file=/var/run/mysqld/edoc.pid \
    --skip-name-resolve \
    >> "$DB_LOG" 2>&1 &
DB_PID=$!
echo "$DB_PID" > "$OUTPUT_DIR/.mariadb.pid"

# Wait for the socket to accept connections.
READY=""
for _ in $(seq 1 60); do
  if mariadb --no-defaults -uroot --socket="$SOCKET" -e "SELECT 1" >/dev/null 2>&1; then
    READY="yes"; break
  fi
  sleep 1
done
if [ -z "$READY" ]; then
  log "FAILED: mariadb did not become ready"; tail -n 40 "$DB_LOG" || true; echo "FAILED"; exit 1
fi
log "mariadb ready"

# --- 2. Create database + user + load schema ---------------------------------
log "creating database/user and loading schema"
mariadb --no-defaults -uroot --socket="$SOCKET" <<'SQL' >> "$DB_LOG" 2>&1
CREATE DATABASE IF NOT EXISTS edoc CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'edoc'@'127.0.0.1' IDENTIFIED BY 'edoc';
CREATE USER IF NOT EXISTS 'edoc'@'localhost' IDENTIFIED BY 'edoc';
CREATE USER IF NOT EXISTS 'edoc'@'%' IDENTIFIED BY 'edoc';
GRANT ALL PRIVILEGES ON edoc.* TO 'edoc'@'127.0.0.1';
GRANT ALL PRIVILEGES ON edoc.* TO 'edoc'@'localhost';
GRANT ALL PRIVILEGES ON edoc.* TO 'edoc'@'%';
FLUSH PRIVILEGES;
SQL

# Load schema from the workspace copy (agent is told not to change schema, but we
# always reload a clean seed so each run starts deterministically).
SQL_FILE="$WORKSPACE_DIR/SQL_Database_edoc.sql"
if [ ! -f "$SQL_FILE" ]; then
  log "FAILED: schema file missing at $SQL_FILE"; echo "FAILED"; exit 1
fi
mariadb --no-defaults -uroot --socket="$SOCKET" edoc < "$SQL_FILE" >> "$DB_LOG" 2>&1 || {
  log "FAILED: loading schema"; tail -n 40 "$DB_LOG" || true; echo "FAILED"; exit 1; }

# Verify a key table exists (service-ready != schema-ready).
if ! mariadb --no-defaults -uroot --socket="$SOCKET" edoc -e "SELECT 1 FROM appointment LIMIT 1" >/dev/null 2>&1; then
  log "FAILED: appointment table not present after load"; echo "FAILED"; exit 1
fi
log "schema loaded"

# --- 3. Start the PHP app ----------------------------------------------------
export DB_HOST="127.0.0.1" DB_PORT="3306" DB_NAME="edoc" DB_USER="edoc" DB_PASSWORD="edoc"
export APP_BASE_URL="http://localhost:${APP_PORT}"
export ALIPAY_MOCK_MODE="true"

log "starting PHP server on :$APP_PORT serving $WORKSPACE_DIR"
php -d display_errors=On -d output_buffering=4096 -d error_reporting=E_ALL \
    -S 0.0.0.0:"$APP_PORT" -t "$WORKSPACE_DIR" >> "$PHP_LOG" 2>&1 &
PHP_PID=$!
echo "$PHP_PID" > "$OUTPUT_DIR/.php.pid"

# --- 4. Wait for health ------------------------------------------------------
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${APP_PORT}/health.php" >/dev/null 2>&1; then
    log "app healthy at http://localhost:${APP_PORT}"
    echo "READY"
    exit 0
  fi
  sleep 1
done

log "FAILED: app health check never passed"
tail -n 40 "$PHP_LOG" || true
echo "FAILED"
exit 1
