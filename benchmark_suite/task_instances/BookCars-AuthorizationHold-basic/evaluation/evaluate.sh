#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
case_name="${CASE_NAME:-${PAYSKILLS_CASE_NAME:-BookCars-AuthorizationHold-basic}}"
export OUTPUT_DIR="$output_dir" WORKSPACE="$workspace" WORKDIR="$workspace" CASE_NAME="$case_name" PAYSKILLS_CASE_NAME="$case_name"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"
EVAL_COMPOSE_FILE="$output_dir/docker-compose.alipay-eval.yml"
mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1
cleanup(){ docker compose -p bcpreauth-task down --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
run_phase(){ local n="$1"; local o="$2"; shift 2; echo "--- phase: $n ---"; "$@" || echo "WARN: $n crashed"; [[ -f "$o" ]] || printf '{"rubrics":[]}\n' > "$o"; }
write_alipay_compose_override(){
  cat > "$EVAL_COMPOSE_FILE" <<'YAML'
services:
  bc-backend:
    environment:
      BC_ALIPAY_APP_ID: "${BC_ALIPAY_APP_ID}"
      BC_ALIPAY_PRIVATE_KEY: "${BC_ALIPAY_PRIVATE_KEY}"
      BC_ALIPAY_PUBLIC_KEY: "${BC_ALIPAY_PUBLIC_KEY}"
      BC_ALIPAY_GATEWAY: "${BC_ALIPAY_GATEWAY}"
YAML
  export COMPOSE_FILE="$workspace/docker-compose.yml:$EVAL_COMPOSE_FILE"
}
backend_has_alipay_config(){
  docker compose -p bcpreauth-task exec -T bc-backend sh -lc '
    test -n "$BC_ALIPAY_APP_ID" &&
    test -n "$BC_ALIPAY_PRIVATE_KEY" &&
    test -n "$BC_ALIPAY_PUBLIC_KEY" &&
    test -n "$BC_ALIPAY_GATEWAY"
  ' >/dev/null 2>&1
}
run_phase static "$checks_dir/static_results.json" python3 "$deterministic_dir/static.py" "$workspace" "$checks_dir/static_results.json" "$case_name"

sandbox_keys_file="${ALIPAY_SANDBOX_KEYS_FILE:-$workspace/alipay-sandbox-keys.json}"
if [[ ! -s "$sandbox_keys_file" ]]; then
  payskills-result fallback --reason "missing alipay sandbox runtime input" --output "$output_dir/result.json"
  cat "$output_dir/result.json"
  exit 0
fi
if ! IFS=$'\t' read -r sandbox_app_id sandbox_private_key sandbox_public_key sandbox_gateway < <(
  python3 - "$sandbox_keys_file" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
data = json.loads(src.read_text(encoding="utf-8"))
app_id = str(data.get("app_id") or "").strip()
private_key = str(
    data.get("merchant_private_key_pkcs1")
    or data.get("merchant_private_key_pkcs8")
    or ""
).strip()
public_key = str(data.get("alipay_public_key") or "").strip()
gateway = str(
    data.get("gateway") or "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
).strip()
if not app_id or not private_key or not public_key:
    raise SystemExit("alipay sandbox runtime input is incomplete")
print("\t".join((app_id, private_key, public_key, gateway)))
PY
); then
  payskills-result fallback --reason "invalid alipay sandbox runtime input" --output "$output_dir/result.json"
  cat "$output_dir/result.json"
  exit 0
fi

export ALIPAY_APP_ID="$sandbox_app_id"
export BC_ALIPAY_APP_ID="$ALIPAY_APP_ID"
export BC_ALIPAY_PRIVATE_KEY="$sandbox_private_key"
export BC_ALIPAY_PUBLIC_KEY="$sandbox_public_key"
export BC_ALIPAY_GATEWAY="$sandbox_gateway"
write_alipay_compose_override

SERVICES_UP=false
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if bash "$deterministic_dir/support/scripts/start_services.sh" "$workspace" "$output_dir" 2>&1 | tee "$output_dir/services_start.log"; then
    [[ "${PIPESTATUS[0]}" -eq 0 ]] && SERVICES_UP=true
  fi
  if [[ "$SERVICES_UP" != true ]] && curl -sf http://localhost:9102/api/settings >/dev/null 2>&1; then SERVICES_UP=true; fi
  if [[ "$SERVICES_UP" == true ]] && ! backend_has_alipay_config; then
    echo "INFRA: canonical Alipay runtime configuration was not injected into bc-backend"
    SERVICES_UP=false
  fi
else
  echo "INFRA: docker daemon not available"
fi
if [[ "$SERVICES_UP" == true ]]; then
  run_phase integration "$checks_dir/integration_results.json" python3 "$deterministic_dir/integration.py" "$workspace" "$checks_dir/integration_results.json" "$case_name"
  run_phase e2e "$checks_dir/e2e_results.json" python3 "$deterministic_dir/e2e.py" "$workspace" "$checks_dir/e2e_results.json" "$case_name"
else
  python3 "$deterministic_dir/support/write_fallback.py" integration "$case_name" "$checks_dir/integration_results.json"
  python3 "$deterministic_dir/support/write_fallback.py" e2e "$case_name" "$checks_dir/e2e_results.json"
fi
run_phase llm "$checks_dir/llm_review_results.json" python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm_review_results.json" "$case_name" "$task_instance_dir"
payskills-result compose --rubric-file "$task_instance_dir/evaluation/rubrics.json" --input "$checks_dir/static_results.json" --input "$checks_dir/integration_results.json" --input "$checks_dir/e2e_results.json" --input "$checks_dir/llm_review_results.json" --agent-file "$artifacts_dir/agent_usage.json" --output "$output_dir/result.json" || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"
python3 "$deterministic_dir/support/postprocess_result.py" "$output_dir" "$case_name" || true
cat "$output_dir/result.json"
exit 0
