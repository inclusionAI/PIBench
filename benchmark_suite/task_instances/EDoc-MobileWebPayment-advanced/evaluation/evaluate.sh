#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
app_port="${APP_PORT:-8136}"

mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

cleanup() {
  [[ -f "$output_dir/.php.pid" ]] && kill "$(cat "$output_dir/.php.pid")" 2>/dev/null || true
  [[ -f "$output_dir/.mariadb.pid" ]] && kill "$(cat "$output_dir/.mariadb.pid")" 2>/dev/null || true
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
export WORKSPACE_DIR="$workspace"
export APP_PORT="$app_port"
export EDOC_BASE_URL="http://localhost:${app_port}"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"

if ! python3 -c "import pytest, requests" >/dev/null 2>&1; then
  python3 -m pip install -q -r "$deterministic_dir/support/requirements.txt" || true
fi

app_marker="$(bash "$deterministic_dir/support/scripts/start_app.sh" 2>>"$output_dir/logs/test_output.txt" | tail -n 1)"
echo "$app_marker" > "$output_dir/app_status.txt"
app_started=false
[[ "$app_marker" == "READY" ]] && app_started=true

run_phase static "$checks_dir/static_results.json" \
  python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static_results.json" "$task_instance_dir"
run_phase integration "$checks_dir/integration_results.json" \
  python3 "$deterministic_dir/integration.py" "$checks_dir/integration_results.json" "$task_instance_dir" "$output_dir" "$app_started"
run_phase llm "$checks_dir/llm_results.json" \
  python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm_results.json" "$task_instance_dir"

payskills-result compose \
  --rubric-file "$task_instance_dir/evaluation/rubrics.json" \
  --input "$checks_dir/static_results.json" \
  --input "$checks_dir/integration_results.json" \
  --input "$checks_dir/llm_results.json" \
  --agent-file "$artifacts_dir/agent_usage.json" \
  --output "$output_dir/result.json" \
  || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"

cat "$output_dir/result.json"
exit 0
