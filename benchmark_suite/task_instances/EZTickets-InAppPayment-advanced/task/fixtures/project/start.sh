#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
BACKEND_DIR="${BACKEND_DIR:-$WORKSPACE/ez_tickets_backend}"
DB_NAME="${DB_DATABASE:-ez_tickets}"
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASS:-}"
PORT="${PORT:-3331}"
HOST="${HOST:-0.0.0.0}"

mkdir -p /var/run/mysqld /var/lib/mysql
chown -R mysql:mysql /var/run/mysqld /var/lib/mysql 2>/dev/null || true

echo "Starting local MySQL..."
if ! mysqladmin ping -h 127.0.0.1 -u root --silent >/dev/null 2>&1; then
  mysqld_safe --datadir=/var/lib/mysql --bind-address=127.0.0.1 >/tmp/ez_tickets_mysql.log 2>&1 &
fi

for _ in $(seq 1 60); do
  if mysqladmin ping -h 127.0.0.1 -u root --silent >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! mysqladmin ping -h 127.0.0.1 -u root --silent >/dev/null 2>&1; then
  echo "MySQL failed to start"
  tail -200 /tmp/ez_tickets_mysql.log 2>/dev/null || true
  exit 1
fi

echo "Preparing database..."
mysql -h 127.0.0.1 -u "$DB_USER" ${DB_PASS:+-p"$DB_PASS"} -e "DROP DATABASE IF EXISTS \`$DB_NAME\`; CREATE DATABASE \`$DB_NAME\`;"
mysql -h 127.0.0.1 -u "$DB_USER" ${DB_PASS:+-p"$DB_PASS"} "$DB_NAME" < "$BACKEND_DIR/ez_tickets.sql"

echo "Installing backend dependencies..."
cd "$BACKEND_DIR"
npm ci || npm install

echo "Starting backend..."
export HOST PORT
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-3306}"
export DB_USER DB_PASS DB_DATABASE="$DB_NAME"
export SECRET_JWT="${SECRET_JWT:-local_dev_secret}"
export SENDGRID_API_KEY="${SENDGRID_API_KEY:-SG.local_dev_dummy}"
export SENDGRID_SENDER="${SENDGRID_SENDER:-dev@example.com}"

npm start >/tmp/ez_tickets_backend.log 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
    echo "Service ready on http://127.0.0.1:$PORT"
    if [ "${BLOCK:-false}" = "true" ]; then
      wait "$BACKEND_PID"
    fi
    exit 0
  fi
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Backend exited before becoming ready"
    tail -200 /tmp/ez_tickets_backend.log 2>/dev/null || true
    exit 1
  fi
  sleep 2
done

echo "Service failed to become ready"
tail -200 /tmp/ez_tickets_backend.log 2>/dev/null || true
exit 1
