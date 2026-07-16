#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"

mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
[[ -f "$artifacts_dir/agent_usage.json" ]] && cp "$artifacts_dir/agent_usage.json" "$output_dir/agent_usage.json"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

run_phase() {
  local name="$1"
  local outfile="$2"
  shift 2
  echo "--- phase: $name ---"
  "$@" || echo "WARN: $name crashed"
  [[ -f "$outfile" ]] || printf '{"rubrics":[],"metadata":{"phase":"%s","missing":true}}\n' "$name" > "$outfile"
}

cleanup() {
  [[ -f "$output_dir/backend.pid" ]] && kill "$(cat "$output_dir/backend.pid")" >/dev/null 2>&1 || true
  [[ -f "$output_dir/mock_gateway.pid" ]] && kill "$(cat "$output_dir/mock_gateway.pid")" >/dev/null 2>&1 || true
}
trap cleanup EXIT

export OUTPUT_DIR="$output_dir"
export WORKSPACE="$workspace"
export WORKSPACE_ROOT="$workspace"
export PROJECT_DIR="$workspace"
export WORKDIR="$workspace"
export TASK_INSTANCE_DIR="$task_instance_dir"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"

sandbox_keys_file="${ALIPAY_SANDBOX_KEYS_FILE:-$workspace/alipay-sandbox-keys.json}"
if [[ -s "$sandbox_keys_file" ]]; then
  sandbox_seller_id="$(python3 - "$sandbox_keys_file" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("seller_id") or "")
PY
)"
  if [[ -n "$sandbox_seller_id" ]]; then
    export ALIPAY_SELLER_ID="$sandbox_seller_id"
  fi
fi

run_phase static "$checks_dir/static.json" \
  python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static.json"
run_phase integration "$checks_dir/integration.json" \
  python3 "$deterministic_dir/integration.py" "$workspace" "$checks_dir/integration.json"
run_phase e2e "$checks_dir/e2e.json" \
  python3 "$deterministic_dir/e2e.py" "$workspace" "$checks_dir/e2e.json"
run_phase llm "$checks_dir/llm.json" \
  python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm.json" "$task_instance_dir"

if python3 "$deterministic_dir/support/build_result.py" "$output_dir"; then
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
