#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
checks_dir="$output_dir/checks"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
case_name="${CASE_NAME:-${PAYSKILLS_CASE_NAME:-BookCars-AuthorizationHold-advanced}}"
export OUTPUT_DIR="$output_dir" WORKSPACE="$workspace" WORKDIR="$workspace" CASE_NAME="$case_name" PAYSKILLS_CASE_NAME="$case_name"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"
KEYS_DIR="${KEYS_DIR:-/tmp/alipay_keys}"
MOCK_PORT="${MOCK_PORT:-19876}"
MOCK_LOG="${MOCK_LOG:-/tmp/mock_gateway_requests.jsonl}"
MOCK_PID=""
mkdir -p "$checks_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1
cleanup(){ [[ -n "${MOCK_PID:-}" ]] && kill "$MOCK_PID" 2>/dev/null || true; docker compose -p bcpreauth-task down --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
run_phase(){ local n="$1"; local o="$2"; shift 2; echo "--- phase: $n ---"; "$@" || echo "WARN: $n crashed"; [[ -f "$o" ]] || printf '{"rubrics":[]}\n' > "$o"; }
EVAL_COMPOSE_FILE="$output_dir/docker-compose.alipay-eval.yml"
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
python3 "$deterministic_dir/support/sign_utils.py" genkeys "$KEYS_DIR" 2>&1 | tee -a "$output_dir/logs/test_output.txt" || true
sandbox_keys_file="${ALIPAY_SANDBOX_KEYS_FILE:-$workspace/alipay-sandbox-keys.json}"
if [[ ! -s "$sandbox_keys_file" ]]; then
  payskills-result fallback --reason "missing alipay sandbox runtime input" --output "$output_dir/result.json"
  cat "$output_dir/result.json"
  exit 0
fi
if ! python3 - "$sandbox_keys_file" "$KEYS_DIR" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
keys_dir = Path(sys.argv[2])
data = json.loads(src.read_text(encoding="utf-8"))
app_id = str(data.get("app_id") or "").strip()
private_key = str(
    data.get("merchant_private_key_pkcs1")
    or data.get("merchant_private_key_pkcs8")
    or ""
).strip()
if not app_id:
    raise SystemExit("alipay sandbox runtime input missing app_id")
if not private_key:
    raise SystemExit("alipay sandbox runtime input missing merchant private key")
keys_dir.mkdir(parents=True, exist_ok=True)
(keys_dir / "sandbox_app_id.txt").write_text(app_id, encoding="utf-8")
(keys_dir / "sandbox_merchant_private_b64.txt").write_text(private_key, encoding="utf-8")
PY
then
  payskills-result fallback --reason "invalid alipay sandbox runtime input" --output "$output_dir/result.json"
  cat "$output_dir/result.json"
  exit 0
fi
sandbox_app_id="$(cat "$KEYS_DIR/sandbox_app_id.txt" 2>/dev/null || true)"
sandbox_merchant_private_b64="$(cat "$KEYS_DIR/sandbox_merchant_private_b64.txt" 2>/dev/null || true)"
export ALIPAY_APP_ID="$sandbox_app_id"
export BC_ALIPAY_APP_ID="$sandbox_app_id"
export MOCK_LOG_FILE="$MOCK_LOG"
python3 "$deterministic_dir/support/mock_alipay_gateway.py" --keys-dir "$KEYS_DIR" --port "$MOCK_PORT" --log-file "$MOCK_LOG" &
MOCK_PID=$!
sleep 2
BACKEND_UP=false; FRONTEND_UP=false
ALIPAY_PUB_B64="$(cat "$KEYS_DIR/alipay_public_b64.txt" 2>/dev/null || true)"
if [[ -z "$sandbox_app_id" || -z "$sandbox_merchant_private_b64" || -z "$ALIPAY_PUB_B64" ]]; then
  payskills-result fallback --reason "sandbox or mock Alipay key material is incomplete" --output "$output_dir/result.json"
  cat "$output_dir/result.json"
  exit 0
fi
export BC_ALIPAY_PRIVATE_KEY="$sandbox_merchant_private_b64"
export BC_ALIPAY_PUBLIC_KEY="$ALIPAY_PUB_B64"
export BC_ALIPAY_GATEWAY="http://host.docker.internal:$MOCK_PORT/gateway.do"
write_alipay_compose_override

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  python3 - <<PY
import sys
try:
    import yaml
except ImportError:
    raise SystemExit(0)
dc_path = "$workspace/docker-compose.yml"
try:
    with open(dc_path, encoding="utf-8") as f:
        dc = yaml.safe_load(f) or {}
    for svc_name, svc in (dc.get("services") or {}).items():
        if "backend" in svc_name.lower() or "api" in svc_name.lower():
            extra_hosts = svc.get("extra_hosts") or []
            if "host.docker.internal:host-gateway" not in extra_hosts:
                extra_hosts.append("host.docker.internal:host-gateway")
                svc["extra_hosts"] = extra_hosts
    with open(dc_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(dc, f, default_flow_style=False, sort_keys=False)
    print("Injected extra_hosts into docker-compose.yml")
except Exception as exc:
    print(f"WARNING: {exc}")
PY
  if bash "$deterministic_dir/support/scripts/start_services.sh" "$workspace" "$output_dir" 2>&1 | tee "$output_dir/services_start.log"; then
    [[ -f "$output_dir/backend_ready" ]] && BACKEND_UP=true
    [[ -f "$output_dir/frontend_ready" ]] && FRONTEND_UP=true
  fi
  if [[ "$BACKEND_UP" != true ]] && curl -sf http://localhost:9102/api/settings >/dev/null 2>&1; then BACKEND_UP=true; fi
  if [[ "$FRONTEND_UP" != true ]] && curl -sf http://localhost:9104/ >/dev/null 2>&1; then FRONTEND_UP=true; fi
  if [[ "$BACKEND_UP" == true ]] && ! backend_has_alipay_config; then
    echo "INFRA: canonical Alipay runtime configuration was not injected into bc-backend"
    BACKEND_UP=false
    FRONTEND_UP=false
  fi
else
  echo "INFRA: docker daemon not available"
fi
if [[ "$BACKEND_UP" == true ]]; then
  run_phase integration "$checks_dir/integration_results.json" python3 "$deterministic_dir/integration.py" "$workspace" "$checks_dir/integration_results.json" "$case_name" "$KEYS_DIR"
else
  python3 "$deterministic_dir/support/write_fallback.py" integration "$case_name" "$checks_dir/integration_results.json"
fi
if [[ "$BACKEND_UP" == true && "$FRONTEND_UP" == true ]]; then
  run_phase e2e "$checks_dir/e2e_results.json" python3 "$deterministic_dir/e2e.py" "$workspace" "$checks_dir/e2e_results.json" "$case_name"
else
  python3 "$deterministic_dir/support/write_fallback.py" e2e "$case_name" "$checks_dir/e2e_results.json"
fi
run_phase llm "$checks_dir/llm_review_results.json" python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$checks_dir/llm_review_results.json" "$case_name" "$task_instance_dir"
payskills-result compose --rubric-file "$task_instance_dir/evaluation/rubrics.json" --input "$checks_dir/static_results.json" --input "$checks_dir/integration_results.json" --input "$checks_dir/e2e_results.json" --input "$checks_dir/llm_review_results.json" --agent-file "$artifacts_dir/agent_usage.json" --output "$output_dir/result.json" || payskills-result fallback --reason "result compose failed" --output "$output_dir/result.json"
python3 "$deterministic_dir/support/postprocess_result.py" "$output_dir" "$case_name" || true
cat "$output_dir/result.json"
exit 0
