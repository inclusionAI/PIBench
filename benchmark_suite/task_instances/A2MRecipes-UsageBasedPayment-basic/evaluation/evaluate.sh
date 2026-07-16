#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"

task_instance_name_from_toml() {
  sed -n 's/^name *= *"\([^"]*\)".*/\1/p' "$task_instance_dir/task_instance.toml" 2>/dev/null | head -1
}
case_name="${CASE_NAME:-${PAYSKILLS_CASE_NAME:-$(task_instance_name_from_toml || basename "$task_instance_dir")}}"

export OUTPUT_DIR="$output_dir"
export WORKSPACE="$workspace"
export WORKDIR="$workspace"
export CASE_NAME="$case_name"
export PAYSKILLS_CASE_NAME="${PAYSKILLS_CASE_NAME:-$case_name}"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"
export PAYSKILLS_AGENT_EVIDENCE_JSON="$artifacts_dir/agent_evidence.json"

mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

SERVER_PID=""
MOCK_PID=""
cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" >/dev/null 2>&1 || true
  [[ -n "$MOCK_PID" ]] && kill "$MOCK_PID" >/dev/null 2>&1 || true
  pkill -f "node dist/server.js" >/dev/null 2>&1 || true
}
trap cleanup EXIT

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

SERVICE_PORT="${SERVICE_PORT:-5000}"
MOCK_PORT="${A2M_MOCK_PORT:-18402}"
export SERVICE_BASE_URL="http://127.0.0.1:${SERVICE_PORT}"
export A2M_MOCK_LOG="$output_dir/gateway_requests.jsonl"
export A2M_MOCK_MODE_FILE="${A2M_MOCK_MODE_FILE:-/tmp/a2m_mock_mode}"
export A2M_MOCK_PORT="$MOCK_PORT"

if [[ ! -d "$workspace" || ! -f "$workspace/package.json" ]]; then
  echo "FATAL: workspace $workspace missing or empty"
fi
cd "$workspace" 2>/dev/null || true

PNPM="pnpm"
command -v pnpm >/dev/null 2>&1 || PNPM="corepack pnpm"
echo "using pnpm: $($PNPM --version 2>&1 | head -1)"

run_phase static "$checks_dir/static_results.json" \
  python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static_results.json" "$case_name"

mkdir -p "$output_dir"
echo "success" > "$A2M_MOCK_MODE_FILE"
: > "$A2M_MOCK_LOG"
python3 "$deterministic_dir/support/mock_gateway.py" >> "$output_dir/mock_gateway.log" 2>&1 &
MOCK_PID=$!
sleep 1

BUILD_OK=false
START_OK=false
BUILD_MSG=""
if ! kill -0 "$MOCK_PID" 2>/dev/null; then
  BUILD_MSG="mock gateway failed to start (test infra problem), see mock_gateway.log"
else
  echo "---- pnpm install ----"
  if $PNPM install --prefer-offline --reporter=append-only > "$output_dir/install.log" 2>&1; then
    echo "install ok"
  else
    BUILD_MSG="pnpm install failed; tail of install.log: $(tail -c 500 "$output_dir/install.log" 2>/dev/null)"
  fi

  echo "---- pnpm build ----"
  if [[ -z "$BUILD_MSG" ]] && $PNPM build > "$output_dir/build.log" 2>&1; then
    BUILD_OK=true
    echo "build ok"
  else
    [[ -z "$BUILD_MSG" ]] && BUILD_MSG="pnpm build failed; tail of build.log: $(tail -c 800 "$output_dir/build.log" 2>/dev/null)"
  fi

  if $BUILD_OK; then
    PORT="$SERVICE_PORT" \
    DEPLOY_RUN_PORT="$SERVICE_PORT" \
    COZE_PROJECT_ENV=PROD \
    A2M_GATEWAY_URL="http://127.0.0.1:${MOCK_PORT}/gateway.do" \
    A2M_APP_ID="test-app-2026001" \
    A2M_SELLER_ID="test-seller-2026001" \
    A2M_SERVICE_ID="a2m_recipe_service" \
    A2M_MERCHANT_PRIVATE_KEY="$(cat "$deterministic_dir/support/test_keys/merchant_private_key.pem")" \
    A2M_ALIPAY_PUBLIC_KEY="$(cat "$deterministic_dir/support/test_keys/gateway_public_key.pem")" \
    A2M_PAYMENT_AMOUNT="0.01" \
    A2M_PAYMENT_CURRENCY="CNY" \
    A2M_GATEWAY="http://127.0.0.1:${MOCK_PORT}/gateway.do" \
    A2M_PRIVATE_KEY="$(cat "$deterministic_dir/support/test_keys/merchant_private_key.pem")" \
    A2M_MERCHANT_ID="test-seller-2026001" \
    A2M_AMOUNT="0.01" \
    A2M_CURRENCY="CNY" \
    A2M_MERCHANT_KEY="test-merchant-key-2026001" \
    A2M_SECRET="test-payment-secret-2026001" \
    A2M_PAYMENT_GATEWAY_URL="http://127.0.0.1:${MOCK_PORT}/gateway.do" \
    A2M_PAYMENT_APP_ID="test-app-2026001" \
    A2M_PAYMENT_MERCHANT_ID="test-seller-2026001" \
    A2M_PAYMENT_APP_KEY="test-app-key-2026001" \
    A2M_PAYMENT_SECRET="test-payment-secret-2026001" \
    A2M_PAYMENT_SECRET_KEY="test-payment-secret-2026001" \
    A2M_PAY_GATEWAY_URL="http://127.0.0.1:${MOCK_PORT}/gateway.do" \
    A2M_PAY_APP_ID="test-app-2026001" \
    A2M_PAY_MERCHANT_ID="test-seller-2026001" \
    A2M_PAY_SECRET="test-payment-secret-2026001" \
    A2M_PAY_CURRENCY="CNY" \
    A2M_PAY_PRICE="0.01" \
      $PNPM start > "$output_dir/server.log" 2>&1 &
    SERVER_PID=$!
    for i in $(seq 1 60); do
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$SERVICE_BASE_URL/api/recipes" 2>/dev/null || echo 000)"
      if [[ "$code" == "200" ]]; then
        START_OK=true
        break
      fi
      if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        BUILD_MSG="server process exited early; tail of server.log: $(tail -c 800 "$output_dir/server.log" 2>/dev/null)"
        break
      fi
      sleep 3
    done
    if ! $START_OK && [[ -z "$BUILD_MSG" ]]; then
      BUILD_MSG="service did not answer GET /api/recipes with 200 within 180s; tail of server.log: $(tail -c 800 "$output_dir/server.log" 2>/dev/null)"
    fi
  fi
fi

python3 "$deterministic_dir/support/write_build_phase.py" "$checks_dir/build_results.json" "$BUILD_OK" "$START_OK" "$BUILD_MSG"

run_phase integration "$checks_dir/integration_results.json" \
  python3 "$deterministic_dir/integration.py" "$workspace" "$checks_dir/integration_results.json" "$case_name"
run_phase e2e "$checks_dir/e2e_results.json" \
  python3 "$deterministic_dir/e2e.py" "$workspace" "$checks_dir/e2e_results.json" "$case_name"
run_phase llm "$checks_dir/llm_judge_results.json" \
  python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm_judge_results.json" "$case_name" "$task_instance_dir"

payskills-result compose \
  --rubric-file "$task_instance_dir/evaluation/rubrics.json" \
  --input "$checks_dir/static_results.json" \
  --input "$checks_dir/build_results.json" \
  --input "$checks_dir/integration_results.json" \
  --input "$checks_dir/e2e_results.json" \
  --input "$checks_dir/llm_judge_results.json" \
  --agent-file "$artifacts_dir/agent_usage.json" \
  --output "$output_dir/result.json" \
  || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"

python3 "$deterministic_dir/support/postprocess_result.py" "$output_dir" "$artifacts_dir" || true

echo "=== $case_name evaluation finished at $(date -u +%FT%TZ) ==="
exit 0
