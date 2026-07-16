#!/usr/bin/env bash
# Local dev environment for EZ Tickets (no Docker daemon available in this container).
# Usage: ./run_local.sh db [--reset] | backend | all | status
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/ez_tickets_backend"
DATA_DIR="${EZ_MYSQL_DATADIR:-/tmp/ez-mysql-data}"
SOCK="${EZ_MYSQL_SOCKET:-/tmp/ez-mysql.sock}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="ez_tickets"
MYSQL_LOG="${EZ_MYSQL_LOG:-/tmp/ez-mysqld.log}"
BACKEND_LOG="${EZ_BACKEND_LOG:-/tmp/ez-backend.log}"
BACKEND_PID_FILE="/tmp/ez-backend.pid"

MYSQLD="$(command -v mysqld || echo /usr/sbin/mysqld)"
MYSQL="$(command -v mysql || echo mysql)"

user_flag=()
if [ "$(id -u)" = "0" ]; then
    user_flag=(--user=root)
fi

mysql_client() {
    "$MYSQL" --no-defaults -h 127.0.0.1 -P "$DB_PORT" -u root "$@"
}

mysql_running() {
    mysql_client -e "SELECT 1" >/dev/null 2>&1
}

start_db() {
    local reset="${1:-}"
    if [ "$reset" = "--reset" ]; then
        echo "[run_local] resetting MySQL datadir $DATA_DIR"
        pkill -f "mysqld.*$DATA_DIR" 2>/dev/null || true
        sleep 2
        rm -rf "$DATA_DIR"
    fi
    if mysql_running; then
        echo "[run_local] MySQL already running on 127.0.0.1:$DB_PORT"
    else
        if [ ! -d "$DATA_DIR/mysql" ]; then
            echo "[run_local] initializing MySQL datadir at $DATA_DIR"
            mkdir -p "$DATA_DIR"
            "$MYSQLD" --no-defaults "${user_flag[@]}" --initialize-insecure \
                --datadir="$DATA_DIR" >>"$MYSQL_LOG" 2>&1 || {
                echo "[run_local] mysqld --initialize failed, see $MYSQL_LOG" >&2
                return 1
            }
            FRESH_DB=1
        fi
        echo "[run_local] starting mysqld (port $DB_PORT, log $MYSQL_LOG)"
        nohup "$MYSQLD" --no-defaults "${user_flag[@]}" \
            --datadir="$DATA_DIR" \
            --socket="$SOCK" \
            --port="$DB_PORT" \
            --bind-address=127.0.0.1 \
            --pid-file=/tmp/ez-mysqld.pid \
            --sql-mode= \
            --log-error="$MYSQL_LOG" >/dev/null 2>&1 &
        for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
            mysql_running && break
            sleep 2
        done
        if ! mysql_running; then
            echo "[run_local] MySQL failed to start, see $MYSQL_LOG" >&2
            tail -n 30 "$MYSQL_LOG" >&2 || true
            return 1
        fi
    fi
    if ! mysql_client -e "USE $DB_NAME" 2>/dev/null || [ "${FRESH_DB:-0}" = "1" ]; then
        echo "[run_local] creating database $DB_NAME and importing ez_tickets.sql"
        mysql_client -e "DROP DATABASE IF EXISTS $DB_NAME; CREATE DATABASE $DB_NAME CHARACTER SET utf8mb4;" || return 1
        mysql_client --default-character-set=utf8mb4 "$DB_NAME" < "$BACKEND_DIR/ez_tickets.sql" || {
            echo "[run_local] importing ez_tickets.sql failed" >&2
            return 1
        }
    fi
    echo "[run_local] MySQL ready: mysql -h 127.0.0.1 -P $DB_PORT -u root $DB_NAME"
}

start_backend() {
    if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
        echo "[run_local] stopping previous backend (pid $(cat "$BACKEND_PID_FILE"))"
        kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
        sleep 2
    fi
    cd "$BACKEND_DIR"
    if [ ! -d node_modules ]; then
        echo "[run_local] installing backend dependencies (npm install)"
        npm install >>"$BACKEND_LOG" 2>&1 || {
            echo "[run_local] npm install failed, see $BACKEND_LOG" >&2
            return 1
        }
    fi
    echo "[run_local] starting backend on 127.0.0.1:3331 (log $BACKEND_LOG)"
    PORT=3331 HOST=0.0.0.0 \
    DB_HOST=127.0.0.1 DB_PORT="$DB_PORT" DB_USER=root DB_PASS= DB_DATABASE="$DB_NAME" \
    SECRET_JWT="${SECRET_JWT:-local_dev_secret}" \
    SENDGRID_API_KEY="${SENDGRID_API_KEY:-SG.local_dev_dummy}" \
    SENDGRID_SENDER="${SENDGRID_SENDER:-dev@example.com}" \
    nohup npm start >>"$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
        if curl -sf http://127.0.0.1:3331/api/v1/health >/dev/null 2>&1; then
            echo "[run_local] backend healthy: http://127.0.0.1:3331/api/v1/health"
            return 0
        fi
        sleep 2
    done
    echo "[run_local] backend failed to become healthy, see $BACKEND_LOG" >&2
    tail -n 40 "$BACKEND_LOG" >&2 || true
    return 1
}

status() {
    mysql_running && echo "MySQL: UP (127.0.0.1:$DB_PORT)" || echo "MySQL: DOWN"
    curl -sf http://127.0.0.1:3331/api/v1/health >/dev/null 2>&1 \
        && echo "Backend: UP (127.0.0.1:3331)" || echo "Backend: DOWN"
}

case "${1:-all}" in
    db)      start_db "${2:-}" ;;
    backend) start_backend ;;
    all)     start_db "${2:-}" && start_backend ;;
    status)  status ;;
    *)       echo "Usage: $0 {db [--reset]|backend|all|status}" >&2; exit 1 ;;
esac
