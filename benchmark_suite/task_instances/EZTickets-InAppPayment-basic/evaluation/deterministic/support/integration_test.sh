#!/usr/bin/env bash
# Integration tests I1-I7: fresh MySQL + agent-modified backend + real Alipay sandbox.
# Writes /output/checks/integration.json (via itest_driver.py).
set -uo pipefail

SUPPORT_DIR="${SUPPORT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
TASK_INSTANCE_DIR="${TASK_INSTANCE_DIR:-$(cd "$SUPPORT_DIR/../../.." && pwd)}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
WORKSPACE="${WORKSPACE:-/workspace}"
BACKEND_DIR="$WORKSPACE/ez_tickets_backend"
CHECKS_FILE="$OUTPUT_DIR/checks/integration.json"

DATA_DIR=/tmp/ez-mysql-itest
SOCK=/tmp/ez-mysql-itest.sock
DB_PORT=3306
MYSQL_LOG="$OUTPUT_DIR/mysql_itest.log"

MYSQLD="$(command -v mysqld || echo /usr/sbin/mysqld)"
user_flag=()
[ "$(id -u)" = "0" ] && user_flag=(--user=root)

mysql_client() {
    mysql --no-defaults -h 127.0.0.1 -P "$DB_PORT" -u root "$@"
}

write_all_failed() {
    # $1 = message, $2 = infra(0/1)
    INFRA="$2" MSG="$1" python3 - "$CHECKS_FILE" <<'PY'
import json, os, sys
msg, infra = os.environ["MSG"], os.environ["INFRA"] == "1"
rubrics = [
    {"id": "I1", "name": "后端基础测试（npm test）"},
    {"id": "I2", "name": "创建合法 App 支付请求"},
    {"id": "I3", "name": "真实沙箱查询响应"},
    {"id": "I4", "name": "支付宝未成功时不确认订单"},
    {"id": "I5", "name": "支付成功后确认绑定 booking"},
    {"id": "I6", "name": "支付确认不误确认其他 booking"},
    {"id": "I7", "name": "App 支付金额来自服务端 booking"},
]
for r in rubrics:
    r.update({"dimension": "functionality", "type": "hard", "passed": False,
              "score": 0, "max_score": 1, "message": msg,
              "evidence": ["backend.log", "mysql_itest.log", "test_output.txt"]})
json.dump({"rubrics": rubrics, "infra_failure": infra},
          open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
}

echo "[itest] stopping agent-phase services"
pkill -f "src/server.js" 2>/dev/null || true
pkill -x mysqld 2>/dev/null || true
pkill -f mysqld 2>/dev/null || true
sleep 3
rm -rf "$DATA_DIR"

echo "[itest] starting fresh MySQL (datadir $DATA_DIR)"
mkdir -p "$DATA_DIR"
if ! "$MYSQLD" --no-defaults "${user_flag[@]}" --initialize-insecure \
        --datadir="$DATA_DIR" >>"$MYSQL_LOG" 2>&1; then
    echo "[itest] INFRA: mysqld --initialize failed, see mysql_itest.log"
    touch "$OUTPUT_DIR/.infra_failure_env"
    write_all_failed "评测环境 MySQL 初始化失败（infra，非 agent 问题），见 mysql_itest.log" 1
    exit 0
fi
nohup "$MYSQLD" --no-defaults "${user_flag[@]}" \
    --datadir="$DATA_DIR" --socket="$SOCK" --port="$DB_PORT" \
    --bind-address=127.0.0.1 --pid-file=/tmp/ez-mysqld-itest.pid \
    --sql-mode= --log-error="$MYSQL_LOG" >/dev/null 2>&1 &
db_up=0
for _ in $(printf '%s ' {1..30}); do
    if mysql_client -e "SELECT 1" >/dev/null 2>&1; then db_up=1; break; fi
    sleep 2
done
if [ "$db_up" != "1" ]; then
    echo "[itest] INFRA: MySQL did not come up, see mysql_itest.log"
    touch "$OUTPUT_DIR/.infra_failure_env"
    write_all_failed "评测环境 MySQL 启动失败（infra，非 agent 问题），见 mysql_itest.log" 1
    exit 0
fi

echo "[itest] importing (possibly agent-modified) ez_tickets.sql"
mysql_client -e "DROP DATABASE IF EXISTS ez_tickets; CREATE DATABASE ez_tickets CHARACTER SET utf8mb4;"
if ! mysql_client --default-character-set=utf8mb4 ez_tickets < "$BACKEND_DIR/ez_tickets.sql" \
        > "$OUTPUT_DIR/sql_import.log" 2>&1; then
    echo "[itest] ez_tickets.sql import failed — likely agent broke the schema, see sql_import.log"
    write_all_failed "ez_tickets.sql 导入失败（可能是 agent 修改 schema 引入语法错误），见 sql_import.log" 0
    exit 0
fi

# --- real Alipay sandbox keys ---
KEYS_JSON="${ALIPAY_SANDBOX_KEYS_FILE:-$WORKSPACE/alipay-sandbox-keys.json}"
if [ ! -f "$KEYS_JSON" ]; then
    echo "[itest] INFRA: alipay-sandbox-keys.json missing"
    touch "$OUTPUT_DIR/.infra_failure_env"
    write_all_failed "缺少支付宝沙箱密钥文件 alipay-sandbox-keys.json（infra），无法执行真实沙箱评测" 1
    exit 0
fi

echo "[itest] loading real Alipay sandbox keys from $KEYS_JSON"
SANDBOX_ENV="$OUTPUT_DIR/alipay_sandbox_env.sh"
if ! node - "$KEYS_JSON" > "$SANDBOX_ENV" <<'JS'
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
function q(v) { return JSON.stringify(String(v == null ? '' : v)); }
const appId = data.app_id || data.appId || '';
const gateway = data.gateway || 'https://openapi-sandbox.dl.alipaydev.com/gateway.do';
const privateKey = data.merchant_private_key_pkcs1 || data.appPrivateKey || data.app_private_key || '';
const privateKeyPkcs8 = data.merchant_private_key_pkcs8 || data.appPrivatePkcsKey || '';
const alipayPublicKey = data.alipay_public_key || data.alipayPublicKey || '';
const signType = data.sign_type || 'RSA2';
for (const [k, v] of Object.entries({
  ALIPAY_APP_ID: appId,
  APP_ID: appId,
  ALIPAY_GATEWAY: gateway,
  ALIPAY_SERVER_URL: gateway,
  ALIPAY_PRIVATE_KEY: privateKey,
  ALIPAY_APP_PRIVATE_KEY: privateKey,
  APP_PRIVATE_KEY: privateKey,
  ALIPAY_PRIVATE_KEY_PKCS8: privateKeyPkcs8,
  ALIPAY_PUBLIC_KEY: alipayPublicKey,
  APP_PUBLIC_KEY: alipayPublicKey,
  ALIPAY_SIGN_TYPE: signType,
  ALIPAY_NOTIFY_URL: 'http://127.0.0.1:3331/api/v1/payments/alipay/notify',
  ALIPAY_RETURN_URL: 'http://127.0.0.1:3331/api/v1/payments/alipay/return',
  ALIPAY_SANDBOX_KEYS_PATH: process.argv[2],
})) {
  console.log(`export ${k}=${q(v)}`);
}
JS
then
    echo "[itest] INFRA: failed to parse sandbox keys"
    touch "$OUTPUT_DIR/.infra_failure_env"
    write_all_failed "支付宝沙箱密钥文件解析失败（infra），见 test_output.txt" 1
    exit 0
fi
. "$SANDBOX_ENV"
if [ -z "${ALIPAY_APP_ID:-}" ] || [ -z "${ALIPAY_PRIVATE_KEY:-}" ] || [ -z "${ALIPAY_PUBLIC_KEY:-}" ]; then
    echo "[itest] INFRA: sandbox keys are incomplete"
    touch "$OUTPUT_DIR/.infra_failure_env"
    write_all_failed "支付宝沙箱密钥不完整（缺 app_id/private_key/public_key），无法执行真实沙箱评测" 1
    exit 0
fi
echo "[itest] real sandbox gateway: $ALIPAY_GATEWAY app_id: $ALIPAY_APP_ID"

# Backend deps (agent may have added alipay-sdk etc.). Always reinstall so
# package.json/package-lock.json changes made by the agent are reflected.
echo "[itest] npm install (refresh backend dependencies)"
( cd "$BACKEND_DIR" && npm install ) >> "$OUTPUT_DIR/npm_install.log" 2>&1 || {
    echo "[itest] npm install failed, see npm_install.log"
    touch "$OUTPUT_DIR/.infra_failure_network"
    write_all_failed "npm install 失败（可能为网络 infra 或 agent 写坏 package.json），见 npm_install.log" 0
    exit 0
}

export PORT=3331 HOST=0.0.0.0 \
    DB_HOST=127.0.0.1 DB_PORT="$DB_PORT" DB_USER=root DB_PASS= DB_DATABASE=ez_tickets \
    SECRET_JWT=local_dev_secret \
    SENDGRID_API_KEY=SG.local_dev_dummy SENDGRID_SENDER=dev@example.com

# --- I1: npm test (before starting the server: mocha requires src/server itself) ---
echo "[itest] I1: running npm test"
I1_PASS=0
if ( cd "$BACKEND_DIR" && npm test ) > "$OUTPUT_DIR/npm_test.log" 2>&1; then
    I1_PASS=1
    echo "[itest] I1 PASS"
else
    echo "[itest] I1 FAIL — see npm_test.log (tail):"
    tail -n 25 "$OUTPUT_DIR/npm_test.log"
fi

echo "[itest] starting backend (npm start), log -> backend.log"
( cd "$BACKEND_DIR" && nohup npm start > "$OUTPUT_DIR/backend.log" 2>&1 & )
backend_up=0
for _ in $(printf '%s ' {1..30}); do
    if curl -sf http://127.0.0.1:3331/api/v1/health >/dev/null 2>&1; then backend_up=1; break; fi
    sleep 2
done

if [ "$backend_up" != "1" ]; then
    echo "[itest] backend did not become healthy — likely the agent broke the server. backend.log tail:"
    tail -n 40 "$OUTPUT_DIR/backend.log" 2>/dev/null
    I1_PASS="$I1_PASS" python3 - "$CHECKS_FILE" <<'PY'
import json, os, sys
i1 = os.environ.get("I1_PASS") == "1"
rubrics = [{"id": "I1", "name": "后端基础测试（npm test）", "passed": i1,
            "message": "" if i1 else "npm test 未通过，见 npm_test.log"},
           {"id": "I2", "name": "创建合法 App 支付请求", "passed": False,
            "message": "后端未能启动（健康检查超时），大概率是改动破坏了服务，见 backend.log"},
           {"id": "I3", "name": "真实沙箱查询响应", "passed": False,
            "message": "后端未启动，无法测试"},
           {"id": "I4", "name": "支付宝未成功时不确认订单", "passed": False,
            "message": "后端未启动，无法测试"},
           {"id": "I5", "name": "支付成功后确认绑定 booking", "passed": False,
            "message": "后端未启动，无法测试"},
           {"id": "I6", "name": "支付确认不误确认其他 booking", "passed": False,
            "message": "后端未启动，无法测试"},
           {"id": "I7", "name": "App 支付金额来自服务端 booking", "passed": False,
            "message": "后端未启动，无法测试"}]
for r in rubrics:
    r.update({"dimension": "functionality", "type": "hard",
              "score": 1 if r["passed"] else 0, "max_score": 1,
              "evidence": ["backend.log", "npm_test.log"]})
json.dump({"rubrics": rubrics, "infra_failure": False},
          open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
    exit 0
fi
echo "[itest] backend healthy"

# --- mint a login-state JWT for seeded user_id=2 (login API depends on
#     deep-email-validator MX/SMTP probes which are unreliable in eval network) ---
TOKEN="$(cd "$BACKEND_DIR" && node -e "console.log(require('jsonwebtoken').sign({user_id:'2'},'local_dev_secret',{expiresIn:'24h'}))")"
if [ -z "$TOKEN" ]; then
    write_all_failed "无法铸造测试 JWT（jsonwebtoken 不可用），见 test_output.txt" 0
    exit 0
fi
echo "[itest] minted JWT for user_id=2 (equivalent login state)"

# --- I2-I4 driver: real sandbox create/query and non-success safety ---
python3 "$SUPPORT_DIR/itest_driver.py" \
    --output-dir "$OUTPUT_DIR" \
    --checks-file "$CHECKS_FILE" \
    --token "$TOKEN" \
    --db-port "$DB_PORT" \
    --i1-pass "$I1_PASS"

# --- I5-I7 driver: deterministic TRADE_SUCCESS through a local signed mock ---
echo "[itest] preparing mock success phase for I5-I7"
MOCK_PORT=18765
MOCK_DIR="$OUTPUT_DIR/mock_alipay_keys"
MOCK_PRIV="$MOCK_DIR/alipay_mock_private.pem"
MOCK_PUB="$MOCK_DIR/alipay_mock_public.pem"
MOCK_LOG="$OUTPUT_DIR/alipay-mock-requests.log"
MOCK_PID=""
mkdir -p "$MOCK_DIR"
if openssl genrsa -out "$MOCK_PRIV" 2048 >/dev/null 2>&1 \
   && openssl rsa -in "$MOCK_PRIV" -pubout -out "$MOCK_PUB" >/dev/null 2>&1; then
    MOCK_PUB_B64=$(awk 'NF && $0 !~ /-----/ {printf "%s", $0}' "$MOCK_PUB")
    node "$SUPPORT_DIR/mock_alipay_gateway.js" "$MOCK_PORT" "$MOCK_PRIV" "$MOCK_LOG" \
        > "$OUTPUT_DIR/alipay_mock_gateway.log" 2>&1 &
    MOCK_PID=$!
    sleep 1

    pkill -f "src/server.js" 2>/dev/null || true
    pkill -f "npm start" 2>/dev/null || true
    sleep 2
    export ALIPAY_GATEWAY="http://127.0.0.1:$MOCK_PORT/gateway.do"
    export ALIPAY_SERVER_URL="$ALIPAY_GATEWAY"
    export ALIPAY_PUBLIC_KEY="$MOCK_PUB_B64"
    export APP_PUBLIC_KEY="$MOCK_PUB_B64"

    echo "[itest] restarting backend against mock gateway $ALIPAY_GATEWAY"
    ( cd "$BACKEND_DIR" && nohup npm start > "$OUTPUT_DIR/backend_mock.log" 2>&1 & )
    mock_backend_up=0
    for _ in $(printf '%s ' {1..30}); do
        if curl -sf http://127.0.0.1:3331/api/v1/health >/dev/null 2>&1; then mock_backend_up=1; break; fi
        sleep 2
    done
    if [ "$mock_backend_up" != "1" ]; then
        echo "[itest] mock backend did not become healthy; I5-I7 will fail in driver"
        tail -n 40 "$OUTPUT_DIR/backend_mock.log" 2>/dev/null || true
    fi
else
    echo "[itest] WARN: mock key generation failed; I5-I7 will run against current backend and fail if success cannot be simulated"
fi

python3 "$SUPPORT_DIR/itest_driver.py" \
    --output-dir "$OUTPUT_DIR" \
    --checks-file "$CHECKS_FILE" \
    --token "$TOKEN" \
    --db-port "$DB_PORT" \
    --mock-success-only

[ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true
exit 0
