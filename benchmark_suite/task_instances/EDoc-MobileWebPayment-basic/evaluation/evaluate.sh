#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
app_port="${APP_PORT:-8136}"
php_pid=""

mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

cleanup() {
  [[ -n "${php_pid:-}" ]] && kill "$php_pid" 2>/dev/null || true
  [[ -f "$workspace/mysqld.bgpid" ]] && kill "$(cat "$workspace/mysqld.bgpid")" 2>/dev/null || true
}
trap cleanup EXIT

run_phase() {
  local name="$1"
  local outfile="$2"
  shift 2
  echo "--- phase: $name ---"
  "$@" || echo "WARN: $name crashed"
  [[ -f "$outfile" ]] || printf '{"rubrics":[],"metadata":{"phase":"%s","missing":true}}\n' "$name" > "$outfile"
}

export OUTPUT_DIR="$output_dir"
export APP_DIR="$workspace"
export DB_HOST="127.0.0.1" DB_PORT="3306" DB_NAME="edoc" DB_USER="edoc" DB_PASSWORD="edoc"
export DB_SOCKET="$workspace/mysql.sock" DB_DATADIR="$workspace/mysql-data"
export EDOC_BASE_URL="http://127.0.0.1:${app_port}"

sandbox_keys_file="${ALIPAY_SANDBOX_KEYS_FILE:-}"
if [[ -n "$sandbox_keys_file" && -f "$sandbox_keys_file" ]]; then
  while IFS= read -r line; do
    eval "export $line"
  done < <(python3 - "$sandbox_keys_file" <<'PY'
import json
import shlex
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = {
    "SANDBOX_APP_ID": data["app_id"],
    "SANDBOX_SELLER_ID": data.get("seller_id") or "",
    "SANDBOX_GATEWAY": data.get("gateway") or "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
    "SANDBOX_MERCHANT_PRIVATE_PKCS1": data.get("merchant_private_key_pkcs1") or data.get("merchant_private_key_pkcs8"),
    "SANDBOX_MERCHANT_PRIVATE_PKCS8": data.get("merchant_private_key_pkcs8") or data.get("merchant_private_key_pkcs1"),
    "SANDBOX_ALIPAY_PUBLIC": data.get("alipay_public_key", ""),
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
  )
fi

export ALIPAY_APP_ID="${ALIPAY_APP_ID:-${SANDBOX_APP_ID:-edoc-h5-sandbox-app}}"
export ALIPAY_SELLER_ID="${ALIPAY_SELLER_ID:-${SANDBOX_SELLER_ID:-edoc-clinic}}"
export ALIPAY_GATEWAY="${ALIPAY_GATEWAY:-${SANDBOX_GATEWAY:-https://openapi-sandbox.dl.alipaydev.com/gateway.do}}"
export ALIPAY_GATEWAY_URL="${ALIPAY_GATEWAY_URL:-$ALIPAY_GATEWAY}"
export ALIPAY_PRIVATE_KEY="${ALIPAY_PRIVATE_KEY:-${SANDBOX_MERCHANT_PRIVATE_PKCS8:-}}"
export ALIPAY_MERCHANT_PRIVATE_KEY="${ALIPAY_MERCHANT_PRIVATE_KEY:-${SANDBOX_MERCHANT_PRIVATE_PKCS8:-}}"
export ALIPAY_MERCHANT_PRIVATE_KEY_PKCS1="${ALIPAY_MERCHANT_PRIVATE_KEY_PKCS1:-${SANDBOX_MERCHANT_PRIVATE_PKCS1:-}}"
export ALIPAY_MERCHANT_PRIVATE_KEY_PKCS8="${ALIPAY_MERCHANT_PRIVATE_KEY_PKCS8:-${SANDBOX_MERCHANT_PRIVATE_PKCS8:-}}"
export ALIPAY_SANDBOX_ALIPAY_PUBLIC_KEY="${ALIPAY_SANDBOX_ALIPAY_PUBLIC_KEY:-${SANDBOX_ALIPAY_PUBLIC:-}}"
export ALIPAY_NOTIFY_URL="${ALIPAY_NOTIFY_URL:-${EDOC_BASE_URL}/alipay/h5/notify.php}"
export ALIPAY_RETURN_URL="${ALIPAY_RETURN_URL:-${EDOC_BASE_URL}/patient/alipay-h5/return.php}"
export ALIPAY_QUIT_URL="${ALIPAY_QUIT_URL:-${EDOC_BASE_URL}/patient/alipay-h5/quit.php}"
export ALIPAY_SANDBOX_VALID_SIGN="${ALIPAY_SANDBOX_VALID_SIGN:-mock-valid}"
export ALIPAY_NOTIFY_FIXTURE_VALID_SIGN="${ALIPAY_NOTIFY_FIXTURE_VALID_SIGN:-$ALIPAY_SANDBOX_VALID_SIGN}"

seed_sql="$workspace/seed.sql"
[[ -f "$seed_sql" ]] || seed_sql="$workspace/SQL_Database_edoc.sql"
[[ -f "$seed_sql" ]] || seed_sql="$task_instance_dir/task/fixtures/project/SQL_Database_edoc.sql"

app_started=false
if bash "$deterministic_dir/support/scripts/start_db.sh" "$seed_sql"; then
  php_log="$output_dir/php_server.log"
  PHP_CLI_SERVER_WORKERS=4 php \
    -d output_buffering=4096 \
    -d display_errors=On \
    -d log_errors=On \
    -S "127.0.0.1:${app_port}" \
    -t "$workspace" \
    "$deterministic_dir/support/scripts/router.php" \
    > "$php_log" 2>&1 &
  php_pid=$!
  for _ in $(seq 1 30); do
    if curl -fsS "${EDOC_BASE_URL}/health.php" >/dev/null 2>&1; then
      app_started=true
      break
    fi
    sleep 1
  done
else
  echo "INFRA: database failed to start"
fi

run_phase static "$checks_dir/static_results.json" \
  python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static_results.json" "$task_instance_dir"
run_phase integration "$checks_dir/integration_results.json" \
  python3 "$deterministic_dir/integration.py" "$checks_dir/integration_results.json" "$task_instance_dir" "$app_started"

payskills-result compose \
  --rubric-file "$task_instance_dir/evaluation/rubrics.json" \
  --input "$checks_dir/static_results.json" \
  --input "$checks_dir/integration_results.json" \
  --agent-file "$artifacts_dir/agent_usage.json" \
  --output "$output_dir/result.json" \
  || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"

cat "$output_dir/result.json"
exit 0
