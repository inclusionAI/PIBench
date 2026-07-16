#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
support_dir="$deterministic_dir/support"
mode="basic"

mkdir -p "$output_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
[[ -f "$artifacts_dir/agent_usage.json" ]] && cp "$artifacts_dir/agent_usage.json" "$output_dir/agent_usage.json"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

export OUTPUT_DIR="$output_dir"
export WORKSPACE="$workspace"
export WORKDIR="$workspace"
export WORK_DIR="$workspace"
export PROJECT_DIR="$workspace"
export TASK_INSTANCE_DIR="$task_instance_dir"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"

pick_free_port() {
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

MOCK_PORT="${ALIPAY_MOCK_PORT:-$(pick_free_port)}"
APP_PORT="${APP_PORT:-$(pick_free_port)}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:${APP_PORT}}"
ALIPAY_MOCK_BASE_URL="${ALIPAY_MOCK_BASE_URL:-http://127.0.0.1:${MOCK_PORT}}"
MOCK_PID=""

cleanup() {
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

dump_project_diagnostics() {
  echo "=== project startup diagnostics ==="
  if [[ -d "$workspace/.case-runtime" ]]; then
    echo "--- .case-runtime files ---"
    find "$workspace/.case-runtime" -maxdepth 2 -type f -printf '%p %s bytes\n' 2>/dev/null || true
  fi
  if [[ -f "$workspace/.case-runtime/app.log" ]]; then
    cp "$workspace/.case-runtime/app.log" "$output_dir/project_app.log" 2>/dev/null || true
    echo "--- tail .case-runtime/app.log ---"
    tail -240 "$workspace/.case-runtime/app.log" || true
  else
    echo "No .case-runtime/app.log found"
  fi
  if [[ -f "$workspace/.case-runtime/app.pid" ]]; then
    cp "$workspace/.case-runtime/app.pid" "$output_dir/project_app.pid" 2>/dev/null || true
    echo "--- .case-runtime/app.pid ---"
    cat "$workspace/.case-runtime/app.pid" || true
  fi
}

finish() {
  trap - EXIT
  if python3 "$support_dir/build_result.py" --mode "$mode" --output-dir "$output_dir"; then
    if ! payskills-result compose \
        --rubric-file "$task_instance_dir/evaluation/rubrics.json" \
        --input "$output_dir/result.json" \
        --metadata-file "$output_dir/result.json" \
        --agent-file "$output_dir/agent_usage.json" \
        --output "$output_dir/result.json"; then
      rm -f "$output_dir/result.json"
      if ! payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"; then
        exit 1
      fi
    fi
  else
    rm -f "$output_dir/result.json"
    if ! payskills-result fallback --reason "result preparation failed" --output "$output_dir/result.json"; then
      exit 1
    fi
  fi
  cat "$output_dir/result.json" || exit 1
  exit 0
}
trap 'cleanup; finish' EXIT

if [[ ! -s "$output_dir/changed_files.txt" ]]; then
  echo "FAIL: agent did not modify any files"
  exit 0
fi

echo "=== starting mock Alipay server on ${ALIPAY_MOCK_BASE_URL} ==="
fuser -k "${MOCK_PORT}/tcp" >/dev/null 2>&1 || true
python3 "$support_dir/tests/mock_alipay_server.py" --host 127.0.0.1 --port "$MOCK_PORT" > "$output_dir/mock_alipay.log" 2>&1 &
MOCK_PID="$!"
for i in $(seq 1 40); do
  if curl -fsS "${ALIPAY_MOCK_BASE_URL}/__mock/state" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
  if [[ "$i" == "40" ]]; then
    echo "WARNING: mock Alipay server did not become ready"
  fi
done

export APP_PORT APP_BASE_URL ALIPAY_MOCK_BASE_URL
export BASE_URL="$APP_BASE_URL"
export ALIPAY_GATEWAY="${ALIPAY_MOCK_BASE_URL}/gateway.do"
export ALIPAY_GATEWAY_URL="${ALIPAY_MOCK_BASE_URL}/gateway.do"
export ALIPAY_APP_ID="${ALIPAY_APP_ID:-case_mock_app}"
export ALIPAY_PID="${ALIPAY_PID:-case_mock_pid}"
export ALIPAY_SELLER_ID="${ALIPAY_SELLER_ID:-case_mock_pid}"
export ALIPAY_SIGN_SCENE="${ALIPAY_SIGN_SCENE:-INDUSTRY|DIGITAL_MEDIA}"
MOCK_ALIPAY_PUBLIC_KEY_FILE="$support_dir/tests/test_keys/mock_alipay_public_key.pem"
MOCK_ALIPAY_PRIVATE_KEY_FILE="$support_dir/tests/test_keys/mock_alipay_private_key.pem"
if [[ -f "$MOCK_ALIPAY_PUBLIC_KEY_FILE" && -f "$MOCK_ALIPAY_PRIVATE_KEY_FILE" ]]; then
  export ALIPAY_PUBLIC_KEY="${ALIPAY_PUBLIC_KEY:-$(cat "$MOCK_ALIPAY_PUBLIC_KEY_FILE")}"
  export ALIPAY_PRIVATE_KEY="${ALIPAY_PRIVATE_KEY:-$(cat "$MOCK_ALIPAY_PRIVATE_KEY_FILE")}"
  export ALIPAY_APP_PRIVATE_KEY="${ALIPAY_APP_PRIVATE_KEY:-$ALIPAY_PRIVATE_KEY}"
  export ALIPAY_APP_PRIVATE_PKCS_KEY="${ALIPAY_APP_PRIVATE_PKCS_KEY:-$ALIPAY_PRIVATE_KEY}"
  export ALIPAY_PUBLIC_KEY_PATH="${ALIPAY_PUBLIC_KEY_PATH:-$MOCK_ALIPAY_PUBLIC_KEY_FILE}"
  export ALIPAY_PRIVATE_KEY_PATH="${ALIPAY_PRIVATE_KEY_PATH:-$MOCK_ALIPAY_PRIVATE_KEY_FILE}"
fi
export ALIPAY_MOCK_MODE="${ALIPAY_MOCK_MODE:-true}"
export ALIPAY_ALLOW_UNSIGNED_NOTIFY="${ALIPAY_ALLOW_UNSIGNED_NOTIFY:-true}"
export PAYSKILLS_TOP_LEVEL_START=1

echo "=== starting project via task fixture start.sh on ${APP_BASE_URL} ==="
START_RC=0
(cd "$workspace" && bash start.sh) > "$output_dir/start_project.log" 2>&1 || START_RC=$?
cat "$output_dir/start_project.log"
if grep -q "APP_READY=" "$output_dir/start_project.log"; then
  echo "=== project ready via start.sh ==="
else
  echo "WARNING: start.sh exit=${START_RC} and APP_READY marker was not observed"
  dump_project_diagnostics
  unset APP_BASE_URL
fi

python3 "$deterministic_dir/static.py" "$workspace" "$output_dir" "$mode" || echo "WARNING: static checks crashed"
python3 "$deterministic_dir/integration.py" "$workspace" "$output_dir" "$mode" "$task_instance_dir" || echo "WARNING: integration checks crashed"
python3 "$deterministic_dir/e2e.py" "$workspace" "$output_dir" "$mode" "$task_instance_dir" || echo "WARNING: e2e checks crashed"
python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$output_dir" "$mode" || echo "WARNING: llm judge crashed"
