#!/usr/bin/env bash
# Start a local MariaDB instance as the (non-root) agent user, using a datadir
# under /workspace so no sudo / system service manager is required. Then create
# the `edoc` database + user and load the seed schema.
#
# Usage: start_db.sh <seed_sql_path>
# Env (with defaults):
#   DB_DATADIR=/workspace/mysql-data
#   DB_SOCKET=/workspace/mysql.sock
#   DB_PORT=3306
#   DB_NAME=edoc DB_USER=edoc DB_PASSWORD=edoc
#   OUTPUT_DIR=/output
set -uo pipefail

SEED_SQL="${1:?seed sql path required}"
DB_DATADIR="${DB_DATADIR:-/workspace/mysql-data}"
DB_SOCKET="${DB_SOCKET:-/workspace/mysql.sock}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-edoc}"
DB_USER="${DB_USER:-edoc}"
DB_PASSWORD="${DB_PASSWORD:-edoc}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
LOG="${OUTPUT_DIR}/db_setup.log"

mkdir -p "$OUTPUT_DIR"
: > "$LOG"
log() { echo "[start_db] $*" | tee -a "$LOG"; }

MYSQLD_BIN="$(command -v mariadbd || command -v mysqld || true)"
INSTALL_BIN="$(command -v mariadb-install-db || command -v mysql_install_db || true)"
CLIENT_BIN="$(command -v mariadb || command -v mysql || true)"
ADMIN_BIN="$(command -v mariadb-admin || command -v mysqladmin || true)"

if [[ -z "$MYSQLD_BIN" || -z "$INSTALL_BIN" || -z "$CLIENT_BIN" ]]; then
  log "FATAL: mariadb binaries missing (mysqld='$MYSQLD_BIN' install='$INSTALL_BIN' client='$CLIENT_BIN')"
  exit 3
fi

mkdir -p "$DB_DATADIR"

# Initialize datadir once.
if [[ ! -d "$DB_DATADIR/mysql" ]]; then
  log "initializing datadir at $DB_DATADIR"
  "$INSTALL_BIN" --no-defaults --datadir="$DB_DATADIR" \
    --auth-root-authentication-method=normal --skip-test-db >>"$LOG" 2>&1 \
    || "$INSTALL_BIN" --no-defaults --datadir="$DB_DATADIR" >>"$LOG" 2>&1 \
    || { log "FATAL: datadir init failed"; exit 3; }
fi

# Launch the server in the background.
log "starting mysqld on 127.0.0.1:${DB_PORT} (socket ${DB_SOCKET})"
"$MYSQLD_BIN" --no-defaults \
  --datadir="$DB_DATADIR" \
  --socket="$DB_SOCKET" \
  --port="$DB_PORT" \
  --bind-address=127.0.0.1 \
  --pid-file=/workspace/mysql.pid \
  --skip-name-resolve >>"$LOG" 2>&1 &
MYSQLD_PID=$!
echo "$MYSQLD_PID" > /workspace/mysqld.bgpid

# Wait until the server answers.
ready=0
for _ in $(seq 1 60); do
  if "$ADMIN_BIN" --no-defaults --socket="$DB_SOCKET" -u root ping >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$MYSQLD_PID" 2>/dev/null; then
    log "FATAL: mysqld exited during startup"
    exit 3
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  log "FATAL: mysqld did not become ready in time"
  exit 3
fi
log "mysqld is ready"

# Create database + user (idempotent) and grant TCP access.
"$CLIENT_BIN" --no-defaults --socket="$DB_SOCKET" -u root >>"$LOG" 2>&1 <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
FLUSH PRIVILEGES;
SQL
if [[ $? -ne 0 ]]; then
  log "FATAL: could not create database/user"
  exit 3
fi

# Load seed schema (drops + recreates tables, so re-runnable).
if [[ -f "$SEED_SQL" ]]; then
  log "loading seed schema from $SEED_SQL"
  "$CLIENT_BIN" --no-defaults --socket="$DB_SOCKET" -u root "$DB_NAME" < "$SEED_SQL" >>"$LOG" 2>&1 \
    || { log "FATAL: seed load failed"; exit 3; }
else
  log "FATAL: seed sql not found at $SEED_SQL"
  exit 3
fi

# Sanity: confirm a core table is queryable over TCP with the app credentials.
if ! "$CLIENT_BIN" --no-defaults -h 127.0.0.1 -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" \
      "$DB_NAME" -e "SELECT COUNT(*) FROM patient;" >>"$LOG" 2>&1; then
  log "FATAL: app-credential TCP query failed (patient table)"
  exit 3
fi

log "database ready: ${DB_NAME} on 127.0.0.1:${DB_PORT}"
exit 0
