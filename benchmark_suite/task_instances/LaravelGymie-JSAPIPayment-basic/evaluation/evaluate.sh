#!/usr/bin/env bash
# Grade the agent's work. Always ends by writing /output/result.json.
set -uo pipefail

TASK_INSTANCE_DIR="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CASE_DIR="$TASK_INSTANCE_DIR/task"
SUPPORT_DIR="$TASK_INSTANCE_DIR/evaluation/deterministic/support"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
WORKSPACE="${WORKSPACE:-/workspace}"
ARTIFACTS_DIR="${PAYSKILLS_ARTIFACTS_DIR:-$OUTPUT_DIR/artifacts}"
PROXY_PORT="${ALIPAY_PROXY_PORT:-8233}"
RUN_FINGERPRINT="$(printf '%s:%s' "$OUTPUT_DIR" "$WORKSPACE" | sha1sum | cut -c1-6)"
APP_PORT="${APP_PORT:-$((18000 + 16#$RUN_FINGERPRINT % 20000))}"
APP_BASE_URL="http://127.0.0.1:${APP_PORT}"
mkdir -p "$OUTPUT_DIR" "$ARTIFACTS_DIR" "$OUTPUT_DIR/logs"
[[ -f "$ARTIFACTS_DIR/patch.diff" ]] && cp "$ARTIFACTS_DIR/patch.diff" "$OUTPUT_DIR/patch.diff"
[[ -f "$ARTIFACTS_DIR/changed_files.txt" ]] && cp "$ARTIFACTS_DIR/changed_files.txt" "$OUTPUT_DIR/changed_files.txt"
[[ -f "$ARTIFACTS_DIR/agent_usage.json" ]] && cp "$ARTIFACTS_DIR/agent_usage.json" "$OUTPUT_DIR/agent_usage.json"

TEST_LOG="$OUTPUT_DIR/test_output.txt"
exec > >(tee -a "$TEST_LOG") 2>&1
echo "=== test.sh start $(date -Is) ==="

if [[ -f "$OUTPUT_DIR/sandbox_env.sh" ]]; then
    # shellcheck disable=SC1090
    source "$OUTPUT_DIR/sandbox_env.sh"
fi
export ALIPAY_KEY_DIR="${ALIPAY_KEY_DIR:-$OUTPUT_DIR/real-alipay-keys}"
export ALIPAY_APP_ID="${REAL_ALIPAY_APP_ID:-${ALIPAY_APP_ID:-}}"
export ALIPAY_SELLER_ID="${REAL_ALIPAY_SELLER_ID:-${ALIPAY_SELLER_ID:-}}"
export ALIPAY_MINIAPP_APP_ID="${REAL_ALIPAY_MINIAPP_APP_ID:-${ALIPAY_MINIAPP_APP_ID:-${ALIPAY_APP_ID:-}}}"
export REAL_ALIPAY_GATEWAY_URL="${REAL_ALIPAY_GATEWAY_URL:-${ALIPAY_REAL_GATEWAY_URL:-https://openapi-sandbox.dl.alipaydev.com/gateway.do}}"
export GATEWAY_LOG="$OUTPUT_DIR/gateway_requests.jsonl"
export ALIPAY_PROXY_PORT="$PROXY_PORT"
export APP_PORT="$APP_PORT"
export APP_BASE_URL="$APP_BASE_URL"
export ALIPAY_SANDBOX_BUYER_ID="${REAL_ALIPAY_SANDBOX_BUYER_ID:-${ALIPAY_SANDBOX_BUYER_ID:-}}"
export ALIPAY_SANDBOX_BUYER_LOGON_ID="${REAL_ALIPAY_SANDBOX_BUYER_LOGON_ID:-${ALIPAY_SANDBOX_BUYER_LOGON_ID:-}}"

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
    exit 0
}
trap finish EXIT

if [[ ! -d "$WORKSPACE" ]]; then
    echo "DIAGNOSIS: workspace $WORKSPACE missing -> run.sh did not complete (infra error, not agent error)"
    echo '{"reason":"workspace missing, run.sh did not prepare environment","stage":"test.sh"}' \
        > "$OUTPUT_DIR/infra_failure.json"
    exit 0
fi

# Keep the real-sandbox logging proxy alive during grading. It forwards to the
# real sandbox; it does not synthesize trade responses.
if ! curl -fsS "http://127.0.0.1:${PROXY_PORT}/__health" >/dev/null 2>&1; then
    echo "real sandbox proxy not running; restarting for grading"
    nohup python3 "$SUPPORT_DIR/real_sandbox_proxy.py" >> "$OUTPUT_DIR/real_sandbox_proxy.log" 2>&1 &
    sleep 2
fi
if ! curl -fsS "http://127.0.0.1:${PROXY_PORT}/__health" >/dev/null 2>&1; then
    echo "DIAGNOSIS: real sandbox proxy cannot start; integration evidence unavailable"
    echo '{"reason":"real sandbox proxy unavailable during grading","stage":"test.sh"}' \
        > "$OUTPUT_DIR/infra_failure.json"
fi

echo "--- static checks (S1-S5) ---"
python3 "$SUPPORT_DIR/static_checks.py" "$WORKSPACE" "$OUTPUT_DIR" \
    || echo "DIAGNOSIS: static_checks.py crashed (test bug, see trace above)"

echo "--- miniapp checks (E1-E3) ---"
python3 "$SUPPORT_DIR/miniapp_checks.py" "$WORKSPACE" "$OUTPUT_DIR" \
    || echo "DIAGNOSIS: miniapp_checks.py crashed (test bug, see trace above)"

echo "--- integration tests (real sandbox create + local invalid-notify check) ---"
python3 "$SUPPORT_DIR/update_env.py" "$WORKSPACE/.env" \
    "APP_URL=$APP_BASE_URL" \
    "ALIPAY_NOTIFY_URL=$APP_BASE_URL/membership-checkout/notify" \
    "ALIPAY_SANDBOX_BUYER_ID=$ALIPAY_SANDBOX_BUYER_ID" \
    "ALIPAY_SANDBOX_BUYER_LOGON_ID=$ALIPAY_SANDBOX_BUYER_LOGON_ID" \
    || echo "DIAGNOSIS: failed to refresh dynamic APP_URL/ALIPAY_NOTIFY_URL in .env"
python3 "$SUPPORT_DIR/integration_tests.py" "$WORKSPACE" "$OUTPUT_DIR" \
    || echo "DIAGNOSIS: integration_tests.py crashed (test bug, see trace above)"

echo "--- LLM code review (L1-L5) ---"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"
python3 "$TASK_INSTANCE_DIR/evaluation/llm_assisted/run_llm_assisted.py" "$WORKSPACE" "$OUTPUT_DIR" \
    || echo "DIAGNOSIS: llm_judge.py crashed (judge rubrics will be missing/invalid)"
