#!/usr/bin/env bash
# Integration tests for the safety case: MySQL + backend + mock Alipay gateway.
# Writes /output/checks/integration.json and /output/checks/unit.json.
set -uo pipefail

SUPPORT_DIR="${SUPPORT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
WORKSPACE_ROOT="${WORKSPACE:-/workspace}"
PROJECT_DIR="${PROJECT_DIR:-$WORKSPACE_ROOT}"
BACKEND_DIR="$PROJECT_DIR/ez_tickets_backend"
CHECKS_DIR="$OUTPUT_DIR/checks"

mkdir -p "$CHECKS_DIR"

SUDO=()
[ "$(id -u)" != "0" ] && SUDO=(sudo -n)
DB_EVAL_USER="${DB_EVAL_USER:-ez_eval}"
DB_EVAL_PASSWORD="${DB_EVAL_PASSWORD:-ez_eval_pw}"
ALIPAY_KEYS_DIR="${ALIPAY_KEYS_DIR:-$OUTPUT_DIR/alipay_keys}"
ALIPAY_MOCK_PORT="${ALIPAY_MOCK_PORT:-8765}"
ALIPAY_MOCK_STATE="${ALIPAY_MOCK_STATE:-$OUTPUT_DIR/alipay_mock_state.json}"
ALIPAY_MOCK_LOG="${ALIPAY_MOCK_LOG:-$OUTPUT_DIR/replay-requests.log}"
export ALIPAY_SELLER_ID="${ALIPAY_SELLER_ID:-2088SELLEREVAL}"

record_infra() {
  touch "$OUTPUT_DIR/$1"
  echo "[infra] $2"
}

write_all_integration_failed() {
  MSG="$1" python3 - "$CHECKS_DIR/integration.json" <<'PY'
import json
import os
import sys

ids = [
    ("I1", "服务可构建启动 / movies 可访问"),
    ("I2", "APP 回调不作为最终成功"),
    ("I3", "失败/取消回调不能覆盖终态"),
    ("I4", "拒绝无效签名通知"),
    ("I5", "通知关键字段校验"),
    ("I6", "用户与订单归属校验"),
    ("I7", "有效通知推进支付成功"),
    ("I8", "查单补偿推进支付成功"),
    ("I9", "处理中状态保持 pending"),
    ("I10", "未确认前禁止重复支付"),
    ("I11", "终态保护"),
    ("I12", "幂等处理"),
    ("I13", "支持支付宝退款"),
    ("I14", "退款请求号策略"),
    ("I15", "区分部分退款与全额退款"),
    ("I16", "金额一致性"),
    ("I17", "通知 app/seller 身份错配必须拒绝"),
    ("I18", "通知买家身份错配必须拒绝"),
    ("I19", "paid 终态不被后续查单降级"),
    ("I20", "fund_change=N 不得当作最终退款成功"),
    ("I21", "退款查询不确定时保持 pending/refunding"),
    ("I22", "同一退款请求号不同金额必须拒绝"),
    ("I23", "多次部分退款累计不得超过已付金额"),
]
rubrics = []
for rid, name in ids:
    rubrics.append({
        "id": rid,
        "name": name,
        "dimension": "security",
        "type": "integration",
        "passed": False,
        "score": 0,
        "max_score": 1,
        "message": os.environ["MSG"],
        "evidence": ["backend.log", "mock_gateway.log", "test_output.txt"],
    })
json.dump({"rubrics": rubrics}, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
}

start_mysql() {
  echo "[itest] starting mysql"
  ${SUDO[@]} mkdir -p /run/mysqld /var/lib/mysql
  ${SUDO[@]} chown -R mysql:mysql /run/mysqld /var/lib/mysql 2>/dev/null || true
  if [ ! -d /var/lib/mysql/mysql ]; then
    ${SUDO[@]} mysqld --initialize-insecure --user=mysql --datadir=/var/lib/mysql > "$OUTPUT_DIR/mysql_init.log" 2>&1 || true
  fi
  if ! mysqladmin ping -h127.0.0.1 --silent 2>/dev/null; then
    ${SUDO[@]} mysqld --user=mysql --datadir=/var/lib/mysql --bind-address=127.0.0.1 --port=3306 \
      --socket=/run/mysqld/mysqld.sock > "$OUTPUT_DIR/mysql.log" 2>&1 &
    for _ in $(seq 1 40); do
      mysqladmin ping -h127.0.0.1 --silent 2>/dev/null && break
      sleep 1
    done
  fi
  mysqladmin ping -h127.0.0.1 --silent 2>/dev/null
}

mysql_root() {
  if mysql --protocol=socket -uroot -e "SELECT 1" >/dev/null 2>&1; then
    mysql --protocol=socket -uroot "$@"
  elif mysql --protocol=TCP -h127.0.0.1 -uroot -e "SELECT 1" >/dev/null 2>&1; then
    mysql --protocol=TCP -h127.0.0.1 -uroot "$@"
  else
    ${SUDO[@]} mysql --protocol=socket -uroot "$@"
  fi
}

mysql_eval() {
  mysql --protocol=TCP -h127.0.0.1 -u"$DB_EVAL_USER" -p"$DB_EVAL_PASSWORD" "$@"
}

import_schema() {
  echo "[itest] importing schema"
  mysql_root -e "CREATE USER IF NOT EXISTS '$DB_EVAL_USER'@'127.0.0.1' IDENTIFIED BY '$DB_EVAL_PASSWORD'; CREATE USER IF NOT EXISTS '$DB_EVAL_USER'@'localhost' IDENTIFIED BY '$DB_EVAL_PASSWORD'; GRANT ALL PRIVILEGES ON *.* TO '$DB_EVAL_USER'@'127.0.0.1' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO '$DB_EVAL_USER'@'localhost' WITH GRANT OPTION; FLUSH PRIVILEGES;" || return 1
  mysql_eval -e "DROP DATABASE IF EXISTS ez_tickets; CREATE DATABASE ez_tickets;" || return 1
  mysql_eval ez_tickets < "$BACKEND_DIR/ez_tickets.sql" > "$OUTPUT_DIR/sql_import.log" 2>&1
}

install_backend_deps() {
  echo "[itest] installing backend dependencies"
  cd "$BACKEND_DIR" || return 1
  rm -rf node_modules

  export npm_config_audit=false
  export npm_config_fund=false
  export npm_config_progress=false
  export npm_config_update_notifier=false
  export npm_config_cache="$OUTPUT_DIR/npm-cache"
  mkdir -p "$npm_config_cache"

  npm --version > "$OUTPUT_DIR/npm_version_before.log" 2>&1 || true
  timeout --kill-after=10s 60s npm install -g npm@10.9.7 --no-audit --no-fund > "$OUTPUT_DIR/npm_self_update.log" 2>&1 || true
  npm --version > "$OUTPUT_DIR/npm_version_after.log" 2>&1 || true
  npm cache clean --force > "$OUTPUT_DIR/npm_cache_clean.log" 2>&1 || true

  echo "[itest] npm install without lockfile via npmjs registry" > "$OUTPUT_DIR/npm_install.log"
  rm -rf node_modules package-lock.json
  timeout --kill-after=10s 300s npm install --include=dev --ignore-scripts --legacy-peer-deps --registry=https://registry.npmjs.org --no-audit --no-fund \
    >> "$OUTPUT_DIR/npm_install.log" 2>&1 || {
      echo "[itest] npm install failed or timed out; targeted repair install" > "$OUTPUT_DIR/npm_install_retry.log"
      rm -rf node_modules package-lock.json
      timeout --kill-after=10s 180s npm install --include=dev --ignore-scripts --legacy-peer-deps --registry=https://registry.npmjs.org --no-audit --no-fund \
        express mysql2 jsonwebtoken bcryptjs cors dotenv alipay-sdk mocha chai supertest qs side-channel \
        >> "$OUTPUT_DIR/npm_install_retry.log" 2>&1 || return 1
    }

  node -e "require('express'); require('alipay-sdk'); require('mocha'); require('qs'); require('side-channel'); console.log('backend deps ok')" \
    > "$OUTPUT_DIR/npm_dependency_check.log" 2>&1 || {
      echo "[itest] dependency check failed; targeted repair install" > "$OUTPUT_DIR/npm_install_repair.log"
      timeout --kill-after=10s 180s npm install --include=dev --ignore-scripts --legacy-peer-deps --registry=https://registry.npmjs.org --no-audit --no-fund express alipay-sdk mocha qs side-channel \
        >> "$OUTPUT_DIR/npm_install_repair.log" 2>&1 || return 1
      node -e "require('express'); require('alipay-sdk'); require('mocha'); require('qs'); require('side-channel'); console.log('backend deps ok')" \
        > "$OUTPUT_DIR/npm_dependency_check.log" 2>&1 || return 1
    }
}

run_backend_unit_tests() {
  echo "[itest] running npm test"
  cd "$BACKEND_DIR" || return 1
  export DB_HOST=127.0.0.1
  export DB_PORT=3306
  export DB_USER="$DB_EVAL_USER"
  export DB_PASSWORD="$DB_EVAL_PASSWORD"
  export DB_PASS="$DB_EVAL_PASSWORD"
  export DB_DATABASE=ez_tickets
  export DB_NAME=ez_tickets
  export SECRET_JWT="${SECRET_JWT:-local_dev_secret}"
  if npm test > "$OUTPUT_DIR/npm_test.log" 2>&1; then
    python3 "$SUPPORT_DIR/unit_checks.py" "$PROJECT_DIR" "$CHECKS_DIR/unit.json" true || true
    return 0
  fi
  tail -40 "$OUTPUT_DIR/npm_test.log" || true
  python3 "$SUPPORT_DIR/unit_checks.py" "$PROJECT_DIR" "$CHECKS_DIR/unit.json" false || true
  return 1
}

generate_alipay_keys() {
  echo "[itest] generating mock alipay keys"
  rm -rf "$ALIPAY_KEYS_DIR"
  mkdir -p "$ALIPAY_KEYS_DIR"
  node "$SUPPORT_DIR/sign_util.js" genkeys "$ALIPAY_KEYS_DIR" || return 1
  node -e '
const fs=require("fs");
const path=require("path");
const k=JSON.parse(fs.readFileSync(path.join(process.argv[1],"keys.json"),"utf8"));
console.log("ALIPAY_APP_ID=eval_app_2026");
console.log("ALIPAY_PRIVATE_KEY="+k.merchant_private_b64);
console.log("ALIPAY_PUBLIC_KEY="+k.alipay_public_b64);
console.log("ALIPAY_NOTIFY_URL=http://127.0.0.1:3331/api/v1/payments/alipay/notify");
' "$ALIPAY_KEYS_DIR" > "$OUTPUT_DIR/alipay.env"
}

start_mock_gateway() {
  echo "[itest] starting mock alipay gateway"
  export ALIPAY_MOCK_KEYS="$ALIPAY_KEYS_DIR"
  export ALIPAY_MOCK_PORT
  export ALIPAY_MOCK_STATE
  export ALIPAY_MOCK_LOG
  : > "$ALIPAY_MOCK_LOG"
  echo '{}' > "$ALIPAY_MOCK_STATE"
  node "$SUPPORT_DIR/mock_alipay_gateway.js" > "$OUTPUT_DIR/mock_gateway.log" 2>&1 &
  MOCK_PID=$!
  echo "$MOCK_PID" > "$OUTPUT_DIR/mock_gateway.pid"
  for _ in $(seq 1 30); do
    curl -fsSL "http://127.0.0.1:$ALIPAY_MOCK_PORT/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  tail -80 "$OUTPUT_DIR/mock_gateway.log" || true
  return 1
}

run_signing_selftest() {
  echo "[itest] running signing self-test"
  export ALIPAY_APP_ID="${ALIPAY_APP_ID:-eval_app_2026}"
  node "$SUPPORT_DIR/sign_util.js" selftest "$ALIPAY_KEYS_DIR" "$BACKEND_DIR" "http://127.0.0.1:$ALIPAY_MOCK_PORT/gateway.do"
}

start_backend() {
  echo "[itest] starting backend"
  cd "$BACKEND_DIR" || return 1
  set -a
  . "$OUTPUT_DIR/alipay.env"
  set +a
  export ALIPAY_GATEWAY="http://127.0.0.1:$ALIPAY_MOCK_PORT/gateway.do"
  export DB_HOST=127.0.0.1
  export DB_PORT=3306
  export DB_USER="$DB_EVAL_USER"
  export DB_PASSWORD="$DB_EVAL_PASSWORD"
  export DB_PASS="$DB_EVAL_PASSWORD"
  export DB_DATABASE=ez_tickets
  export DB_NAME=ez_tickets
  export PORT=3331
  export SECRET_JWT="${SECRET_JWT:-local_dev_secret}"
  npm start > "$OUTPUT_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  echo "$BACKEND_PID" > "$OUTPUT_DIR/backend.pid"
  for _ in $(seq 1 45); do
    curl -fsSL http://127.0.0.1:3331/api/v1/health >/dev/null 2>&1 && return 0
    sleep 1
  done
  tail -120 "$OUTPUT_DIR/backend.log" || true
  return 1
}

run_integration_driver() {
  echo "[itest] running integration driver"
  export BACKEND_BASE=http://127.0.0.1:3331
  export BACKEND_DIR="$BACKEND_DIR"
  export OUTPUT_DIR="$OUTPUT_DIR"
  export SECRET_JWT="${SECRET_JWT:-local_dev_secret}"
  export MYSQL_HOST=127.0.0.1
  export MYSQL_PORT=3306
  export MYSQL_USER="$DB_EVAL_USER"
  export MYSQL_PASSWORD="$DB_EVAL_PASSWORD"
  export MYSQL_DATABASE=ez_tickets
  export DB_HOST=127.0.0.1
  export DB_PORT=3306
  export DB_USER="$DB_EVAL_USER"
  export DB_PASSWORD="$DB_EVAL_PASSWORD"
  export DB_PASS="$DB_EVAL_PASSWORD"
  export DB_DATABASE=ez_tickets
  export DB_NAME=ez_tickets
  export ALIPAY_MOCK_KEYS="$ALIPAY_KEYS_DIR"
  export ALIPAY_MOCK_STATE
  export ALIPAY_MOCK_LOG
  export RESULT_FILE="$OUTPUT_DIR/integration_results.json"
  node "$SUPPORT_DIR/integration_tests.js" || true
  python3 "$SUPPORT_DIR/itest_driver.py" "$OUTPUT_DIR/integration_results.json" "$CHECKS_DIR/integration.json" || true
}

cleanup() {
  for pid_file in "$OUTPUT_DIR/backend.pid" "$OUTPUT_DIR/mock_gateway.pid"; do
    [ -f "$pid_file" ] && kill "$(cat "$pid_file")" >/dev/null 2>&1 || true
  done
}

trap cleanup EXIT

if [ ! -d "$BACKEND_DIR" ]; then
  write_all_integration_failed "工作区缺少 ez_tickets_backend"
  exit 0
fi

install_backend_deps || {
  record_infra .infra_failure_network "backend dependency install failed"
  write_all_integration_failed "backend 依赖安装失败，见 npm_install.log"
  exit 0
}
start_mysql || {
  record_infra .infra_failure_env "mysql did not start"
  write_all_integration_failed "MySQL 启动失败，见 mysql.log"
  exit 0
}
import_schema || {
  write_all_integration_failed "ez_tickets.sql 导入失败，见 sql_import.log"
  exit 0
}
run_backend_unit_tests || true
generate_alipay_keys || {
  write_all_integration_failed "mock Alipay key 生成失败"
  exit 0
}
start_mock_gateway || {
  record_infra .infra_failure_env "mock gateway failed"
  write_all_integration_failed "mock Alipay gateway 启动失败，见 mock_gateway.log"
  exit 0
}
run_signing_selftest || {
  write_all_integration_failed "签名自检失败"
  exit 0
}
start_backend || {
  write_all_integration_failed "后端未能启动或 health 不可访问，见 backend.log"
  exit 0
}
run_integration_driver
exit 0
