#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
deterministic_support_dir="$deterministic_dir/support"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"

task_instance_name_from_toml() {
  sed -n 's/^name *= *"\([^"]*\)".*/\1/p' "$task_instance_dir/task_instance.toml" 2>/dev/null | head -1
}

task_instance_toml_name="$(task_instance_name_from_toml || true)"
case_name="${CASE_NAME:-${PAYSKILLS_CASE_NAME:-${task_instance_toml_name:-$(basename "$task_instance_dir")}}}"

export CASE_DIR="$deterministic_dir"
export OUTPUT_DIR="$output_dir"
export WORKSPACE="$workspace"
export WORKDIR="$workspace"
export CASE_NAME="$case_name"
export PAYSKILLS_CASE_NAME="${PAYSKILLS_CASE_NAME:-$case_name}"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"
export PAYSKILLS_AGENT_EVIDENCE_JSON="$artifacts_dir/agent_evidence.json"

mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

cleanup_runtime() {
  if [[ -n "${MOCK_PID:-}" ]] && kill -0 "$MOCK_PID" 2>/dev/null; then
    kill "$MOCK_PID" 2>/dev/null || true
  fi
  if [[ -f "$workspace/.case-runtime/app.pid" ]]; then
    local app_pid
    app_pid="$(cat "$workspace/.case-runtime/app.pid" 2>/dev/null || true)"
    if [[ -n "$app_pid" ]] && kill -0 "$app_pid" 2>/dev/null; then
      kill "$app_pid" 2>/dev/null || true
    fi
  fi
}
trap cleanup_runtime EXIT

ensure_phase_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    printf '{"rubrics":[],"metadata":{"missing_phase_file":"%s"}}\n' "$(basename "$path")" > "$path"
  fi
}

run_phase() {
  local name="$1"
  local out_file="$2"
  shift 2
  echo "--- phase: $name ---"
  "$@" || echo "WARN: $name crashed; compose will mark missing rubrics"
  ensure_phase_file "$out_file"
}

echo "=== $case_name evaluation started at $(date -u +%FT%TZ) ==="

chmod +x "$workspace/start.sh" 2>/dev/null || true

case "${PAYSKILLS_PRODUCT:-}:${PAYSKILLS_SCENARIO:-}" in
  OrderQRCodePayment:basic) BASE_PORT=21000 ;;
  QRCodePayment:basic) BASE_PORT=22000 ;;
  OrderQRCodePayment:advanced) BASE_PORT=23000 ;;
  QRCodePayment:advanced) BASE_PORT=24000 ;;
  *)
    echo "ERROR: unsupported BillExpress evaluation metadata: product=${PAYSKILLS_PRODUCT:-} scenario=${PAYSKILLS_SCENARIO:-}" >&2
    exit 2
    ;;
esac

APP_PORT="${APP_PORT:-$((BASE_PORT + $$ % 1000))}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:${APP_PORT}}"
MOCK_PORT="${ALIPAY_MOCK_PORT:-$((18080 + $$ % 1000))}"
ALIPAY_MOCK_BASE_URL="${ALIPAY_MOCK_BASE_URL:-http://127.0.0.1:${MOCK_PORT}}"
MOCK_PID=""

echo "=== starting mock Alipay server on ${ALIPAY_MOCK_BASE_URL} ==="
python3 "$deterministic_support_dir/mock_alipay_server.py" --host 127.0.0.1 --port "$MOCK_PORT" > "$output_dir/mock_alipay.log" 2>&1 &
MOCK_PID="$!"
for i in $(seq 1 40); do
  if curl -fsS "${ALIPAY_MOCK_BASE_URL}/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
  if [[ "$i" == "40" ]]; then
    echo "WARNING: mock Alipay server did not become ready"
  fi
done

export APP_PORT APP_BASE_URL ALIPAY_MOCK_BASE_URL
export APP_HOST="${APP_HOST:-127.0.0.1}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-developer}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-developer123}"
export ALIPAY_GATEWAY_URL="${ALIPAY_MOCK_BASE_URL}/gateway.do"
export ALIPAY_GATEWAY="${ALIPAY_GATEWAY:-$ALIPAY_GATEWAY_URL}"
export ALIPAY_APP_ID="${ALIPAY_APP_ID:-mock-app-id}"
export ALIPAY_APP_PRIVATE_KEY_FILE="${ALIPAY_APP_PRIVATE_KEY_FILE:-$deterministic_support_dir/mock_keys/mock_merchant_private_key.pem}"
export ALIPAY_PUBLIC_KEY_FILE="${ALIPAY_PUBLIC_KEY_FILE:-$deterministic_support_dir/mock_keys/mock_alipay_public_key.pem}"
export ALIPAY_MERCHANT_PRIVATE_KEY_PATH="${ALIPAY_MERCHANT_PRIVATE_KEY_PATH:-$ALIPAY_APP_PRIVATE_KEY_FILE}"
export ALIPAY_PUBLIC_KEY_PATH="${ALIPAY_PUBLIC_KEY_PATH:-$ALIPAY_PUBLIC_KEY_FILE}"
export ALIPAY_APP_PRIVATE_KEY_PATH="${ALIPAY_APP_PRIVATE_KEY_PATH:-$ALIPAY_APP_PRIVATE_KEY_FILE}"
export ALIPAY_APP_PUBLIC_KEY_FILE="${ALIPAY_APP_PUBLIC_KEY_FILE:-$deterministic_support_dir/mock_keys/mock_merchant_public_key.pem}"
export ALIPAY_SIGN_TYPE="${ALIPAY_SIGN_TYPE:-RSA2}"
export ALIPAY_KEY_TYPE="${ALIPAY_KEY_TYPE:-PKCS1}"
export ALIPAY_PRIVATE_KEY_TYPE="${ALIPAY_PRIVATE_KEY_TYPE:-PKCS1}"
export ALIPAY_NOTIFY_BASE_URL="${ALIPAY_NOTIFY_BASE_URL:-$APP_BASE_URL}"
export ALIPAY_NOTIFY_URL="${ALIPAY_NOTIFY_URL:-$APP_BASE_URL/alipay/notify/order-code}"
export ALIPAY_TIMEOUT_MS="${ALIPAY_TIMEOUT_MS:-5000}"
export PAYSKILLS_TOP_LEVEL_START=1

mkdir -p "$workspace/.case-runtime"
export ALIPAY_EVAL_CONFIG="${ALIPAY_EVAL_CONFIG:-$workspace/.case-runtime/alipay-sandbox-keys.json}"
export ALIPAY_PRIVATE_KEY="${ALIPAY_PRIVATE_KEY:-$(cat "$ALIPAY_APP_PRIVATE_KEY_FILE")}"
export ALIPAY_APP_PRIVATE_KEY="${ALIPAY_APP_PRIVATE_KEY:-$ALIPAY_PRIVATE_KEY}"
export ALIPAY_APP_PRIVATE_PKCS_KEY="${ALIPAY_APP_PRIVATE_PKCS_KEY:-$ALIPAY_PRIVATE_KEY}"
export ALIPAY_MERCHANT_PRIVATE_KEY="${ALIPAY_MERCHANT_PRIVATE_KEY:-$ALIPAY_PRIVATE_KEY}"
export ALIPAY_PUBLIC_KEY="${ALIPAY_PUBLIC_KEY:-$(cat "$ALIPAY_PUBLIC_KEY_FILE")}"
export ALIPAY_ALIPAY_PUBLIC_KEY="${ALIPAY_ALIPAY_PUBLIC_KEY:-$ALIPAY_PUBLIC_KEY}"
python3 - <<'PY'
import json
import os
from pathlib import Path

private_path = Path(os.environ["ALIPAY_APP_PRIVATE_KEY_FILE"])
public_path = Path(os.environ["ALIPAY_PUBLIC_KEY_FILE"])
private_key = private_path.read_text()
public_key = public_path.read_text()
gateway = os.environ["ALIPAY_GATEWAY_URL"]
app_id = os.environ["ALIPAY_APP_ID"]
config = {
    "appId": app_id,
    "app_id": app_id,
    "gateway": gateway,
    "serverUrl": gateway,
    "privateKey": private_key,
    "appPrivateKey": private_key,
    "appPrivatePkcsKey": private_key,
    "merchantPrivateKey": private_key,
    "alipayPublicKey": public_key,
    "publicKey": public_key,
    "signType": "RSA2",
    "sign_type": "RSA2",
    "keyType": "PKCS1",
    "key_type": "PKCS1",
    "appPrivateKeyPath": str(private_path),
    "merchant_private_key_path": str(private_path),
    "alipayPublicKeyPath": str(public_path),
    "alipay_public_key_path": str(public_path),
}
config_text = json.dumps(config)
Path(os.environ["ALIPAY_EVAL_CONFIG"]).write_text(config_text)
Path(os.environ["WORKSPACE"], "alipay-sandbox-keys.json").write_text(config_text)
PY
export ALIPAY_KEYS_PATH="${ALIPAY_KEYS_PATH:-$ALIPAY_EVAL_CONFIG}"
export ALIPAY_KEYS_FILE="${ALIPAY_KEYS_FILE:-$ALIPAY_EVAL_CONFIG}"
export ALIPAY_CONFIG_PATH="${ALIPAY_CONFIG_PATH:-$ALIPAY_EVAL_CONFIG}"

echo "=== cleaning SQLite runtime artifacts before start.sh ==="
rm -f "$workspace"/data.db*

echo "=== starting project via task fixture start.sh on ${APP_BASE_URL} ==="
START_RC=0
(cd "$workspace" && bash start.sh) > "$output_dir/start_${case_name}.log" 2>&1 || START_RC=$?
cat "$output_dir/start_${case_name}.log"
if grep -q "APP_READY=" "$output_dir/start_${case_name}.log"; then
  echo "=== project ready via start.sh ==="
else
  echo "WARNING: start.sh exit=${START_RC} and APP_READY marker was not observed"
  unset APP_BASE_URL
fi

run_phase static "$checks_dir/static_results.json" \
  python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static_results.json" "$case_name"
run_phase integration "$checks_dir/integration_results.json" \
  python3 "$deterministic_dir/integration.py" "$workspace" "$checks_dir/integration_results.json" "$case_name"
run_phase e2e "$checks_dir/e2e_results.json" \
  python3 "$deterministic_dir/e2e.py" "$workspace" "$checks_dir/e2e_results.json" "$case_name"
run_phase llm "$checks_dir/llm_judge_results.json" \
  python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm_judge_results.json" "$case_name" "$task_instance_dir"

payskills-result compose \
  --rubric-file "$task_instance_dir/evaluation/rubrics.json" \
  --input "$checks_dir/static_results.json" \
  --input "$checks_dir/integration_results.json" \
  --input "$checks_dir/e2e_results.json" \
  --input "$checks_dir/llm_judge_results.json" \
  --agent-file "$artifacts_dir/agent_usage.json" \
  --output "$output_dir/result.json" \
  || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"

echo "=== $case_name evaluation finished at $(date -u +%FT%TZ) ==="
exit 0
