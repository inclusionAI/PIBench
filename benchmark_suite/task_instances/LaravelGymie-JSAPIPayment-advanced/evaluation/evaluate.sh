#!/usr/bin/env bash
set -uo pipefail
TASK_INSTANCE_DIR="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CASE_DIR="$TASK_INSTANCE_DIR/task"
SUPPORT_DIR="$TASK_INSTANCE_DIR/evaluation/deterministic/support"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
PROJECT_DIR="${WORKSPACE:-/workspace}"
ARTIFACTS_DIR="${PAYSKILLS_ARTIFACTS_DIR:-$OUTPUT_DIR/artifacts}"
KEY_DIR="${ALIPAY_KEY_DIR:-$OUTPUT_DIR/alipay-keys}"
GATEWAY_PORT="${GATEWAY_PORT:-8234}"
mkdir -p "$OUTPUT_DIR" "$ARTIFACTS_DIR" "$OUTPUT_DIR/logs"
[[ -f "$ARTIFACTS_DIR/patch.diff" ]] && cp "$ARTIFACTS_DIR/patch.diff" "$OUTPUT_DIR/patch.diff"
[[ -f "$ARTIFACTS_DIR/changed_files.txt" ]] && cp "$ARTIFACTS_DIR/changed_files.txt" "$OUTPUT_DIR/changed_files.txt"
[[ -f "$ARTIFACTS_DIR/agent_usage.json" ]] && cp "$ARTIFACTS_DIR/agent_usage.json" "$OUTPUT_DIR/agent_usage.json"
exec > >(tee -a "$OUTPUT_DIR/test_output.txt") 2>&1
echo "=== test.sh start $(date -Is) ==="
finish() {
  trap - EXIT
  if python3 "$SUPPORT_DIR/build_result.py" "$OUTPUT_DIR"; then
    if ! payskills-result compose \
        --rubric-file "$TASK_INSTANCE_DIR/evaluation/rubrics.json" \
        --input "$OUTPUT_DIR/result.json" \
        --metadata-file "$OUTPUT_DIR/result.json" \
        --agent-file "$OUTPUT_DIR/agent_usage.json" \
        --output "$OUTPUT_DIR/result.json"; then
      rm -f "$OUTPUT_DIR/result.json"
      if ! payskills-result fallback --reason "result compose failed" --output "$OUTPUT_DIR/result.json"; then
        exit 1
      fi
    fi
  else
    rm -f "$OUTPUT_DIR/result.json"
    if ! payskills-result fallback --reason "result preparation failed" --output "$OUTPUT_DIR/result.json"; then
      exit 1
    fi
  fi
  [[ -s "$OUTPUT_DIR/result.json" ]] || exit 1
  echo "=== test.sh done $(date -Is) ==="
}
trap finish EXIT
if [[ ! -d "$PROJECT_DIR" ]]; then
  echo '{"reason":"workspace missing","stage":"test.sh"}' > "$OUTPUT_DIR/infra_failure.json"
  exit 0
fi
cd "$PROJECT_DIR"
php -d memory_limit=512M artisan config:clear >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 || true
php -d memory_limit=768M artisan migrate:fresh --seed --force --ansi > "$OUTPUT_DIR/migrate.log" 2>&1 || echo "migrate failed; integration will report"
echo '--- static checks ---'
python3 "$SUPPORT_DIR/static_checks.py" "$PROJECT_DIR" "$OUTPUT_DIR" || echo 'static_checks crashed'
echo '--- fake alipay gateway ---'
python3 "$SUPPORT_DIR/gen_keys.py" "$KEY_DIR" || echo 'key generation failed; integration will report'
export ALIPAY_KEY_DIR="$KEY_DIR"
export ALIPAY_APP_ID="${ALIPAY_APP_ID:-2021003100000001}"
export GATEWAY_LOG="$OUTPUT_DIR/gateway_requests.jsonl"
export GATEWAY_PORT="$GATEWAY_PORT"
if ! curl -fsS "http://127.0.0.1:${GATEWAY_PORT}/admin/trades" >/dev/null 2>&1; then
  nohup python3 "$SUPPORT_DIR/mock_gateway.py" > "$OUTPUT_DIR/mock_gateway.log" 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    curl -fsS "http://127.0.0.1:${GATEWAY_PORT}/admin/trades" >/dev/null 2>&1 && break
  done
fi
echo '--- integration checks ---'
python3 "$SUPPORT_DIR/integration_tests.py" "$PROJECT_DIR" "$OUTPUT_DIR" || echo 'integration_tests crashed'
