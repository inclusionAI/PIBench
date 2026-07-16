#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
support_dir="$deterministic_dir/support"
app_pid=""

mkdir -p "$output_dir" "$artifacts_dir" "$output_dir/logs"
[[ -f "$artifacts_dir/patch.diff" ]] && cp "$artifacts_dir/patch.diff" "$output_dir/patch.diff"
[[ -f "$artifacts_dir/changed_files.txt" ]] && cp "$artifacts_dir/changed_files.txt" "$output_dir/changed_files.txt"
[[ -f "$artifacts_dir/agent_usage.json" ]] && cp "$artifacts_dir/agent_usage.json" "$output_dir/agent_usage.json"
exec > >(tee -a "$output_dir/logs/test_output.txt") 2>&1

export OUTPUT_DIR="$output_dir"
export WORKSPACE="$workspace"
export WORKDIR="$workspace"
export TASK_INSTANCE_DIR="$task_instance_dir"
PAYSKILLS_JUDGE_DEFAULT_BIN="payskills-judge"
export PAYSKILLS_LLM_JUDGE_BIN="${PAYSKILLS_LLM_JUDGE_BIN:-$PAYSKILLS_JUDGE_DEFAULT_BIN}"

cleanup() {
  [[ -n "${app_pid:-}" ]] && kill "$app_pid" 2>/dev/null || true
  sudo service mysql stop >/dev/null 2>&1 || true
}
trap cleanup EXIT

finish() {
  trap - EXIT
  if python3 "$support_dir/build_result.py" "$output_dir"; then
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
trap finish EXIT

if [[ ! -s "$output_dir/changed_files.txt" ]]; then
  echo "FAIL: agent did not modify any files"
  exit 0
fi

echo "=== Phase 1: Static Checks ==="
python3 "$deterministic_dir/static.py" "$workspace" "$output_dir" || echo "WARNING: static checks crashed"

echo "=== Phase 2: Build & Start ==="
build_ok=false
app_started=false

sudo service mysql start 2>&1 || true
sleep 3
sudo mysql -u root -e "CREATE DATABASE IF NOT EXISTS litemall DEFAULT CHARACTER SET utf8mb4;" 2>&1 || true
sudo mysql -u root -e "CREATE USER IF NOT EXISTS 'litemall'@'localhost' IDENTIFIED BY 'litemall123456';" 2>&1 || true
sudo mysql -u root -e "CREATE USER IF NOT EXISTS 'litemall'@'%' IDENTIFIED BY 'litemall123456';" 2>&1 || true
sudo mysql -u root -e "GRANT ALL PRIVILEGES ON litemall.* TO 'litemall'@'localhost'; GRANT ALL PRIVILEGES ON litemall.* TO 'litemall'@'%'; FLUSH PRIVILEGES;" 2>&1 || true

for sql_file in "$workspace/litemall-db/sql/litemall_schema.sql" \
                "$workspace/litemall-db/sql/litemall_table.sql" \
                "$workspace/litemall-db/sql/litemall_data.sql"; do
  [[ -f "$sql_file" ]] && { echo "Importing: $(basename "$sql_file")"; sudo mysql -u root litemall < "$sql_file" 2>&1 | tail -3; }
done

app_yml="$workspace/docker/litemall/application.yml"
export ALIPAY_NOTIFY_URL="${ALIPAY_NOTIFY_URL:-http://127.0.0.1:8080/wx/order/alipay-notify}"
export ALIPAY_RETURN_URL="${ALIPAY_RETURN_URL:-http://127.0.0.1:8080/vue/index.html#/order/order-list}"
export LITEMALL_WX_NOTIFY_URL="${LITEMALL_WX_NOTIFY_URL:-http://127.0.0.1:8080/wx/order/pay-notify}"
export LITEMALL_STORAGE_PUBLIC_URL="${LITEMALL_STORAGE_PUBLIC_URL:-http://127.0.0.1:8080/wx/storage/fetch/}"
python3 - "$workspace" <<'PYURLPATCH'
import os
import re
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
targets = [
    workspace / "docker/litemall/application.yml",
    workspace / "litemall-core/src/main/resources/application-core.yml",
]
replacements = {
    "jdbc:mysql://mysql:3306/litemall": "jdbc:mysql://localhost:3306/litemall",
}
key_overrides = {
    "notify-url": os.environ["LITEMALL_WX_NOTIFY_URL"],
    "return-url": os.environ["ALIPAY_RETURN_URL"],
    "address": os.environ["LITEMALL_STORAGE_PUBLIC_URL"],
}

def patch_known_config(path: Path) -> None:
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8", errors="replace")
    patched = raw
    for old, new in replacements.items():
        patched = patched.replace(old, new)
    lines = []
    for line in patched.splitlines():
        match = re.match(r"^(\s*)(notify-url|return-url|address)\s*:\s*(.*)$", line)
        if match:
            key = match.group(2)
            value = match.group(3).strip()
            if key == "address" and "/wx/storage/fetch" not in value:
                lines.append(line)
                continue
            lines.append(f"{match.group(1)}{key}: {key_overrides[key]}")
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Patched runtime-local URLs/DB in {path.relative_to(workspace)}")

for target in targets:
    patch_known_config(target)
PYURLPATCH

echo "Building frontend..."
if [[ -d "$workspace/litemall-vue" ]]; then
  cd "$workspace/litemall-vue"
  npm install --legacy-peer-deps > "$output_dir/npm_install.log" 2>&1 \
    && npm run build > "$output_dir/npm_build.log" 2>&1 \
    && echo "Frontend OK"
  mkdir -p "$workspace/litemall-all/src/main/resources/static/vue/"
  [[ -d dist ]] && cp -r dist/* "$workspace/litemall-all/src/main/resources/static/vue/" 2>/dev/null || true
fi

echo "Building backend..."
cd "$workspace"
mvn clean package -DskipTests -q > "$output_dir/maven_build.log" 2>&1 || true
jar_path="$(ls "$workspace"/litemall-all/target/litemall-all-*-exec.jar 2>/dev/null | head -1)"
if [[ -n "$jar_path" ]]; then
  build_ok=true
  echo "BUILD SUCCESS: $jar_path"
else
  echo "BUILD FAILED"
  tail -40 "$output_dir/maven_build.log" 2>/dev/null || true
fi

if [[ "$build_ok" == true ]]; then
  echo "Starting application..."
  cd "$(dirname "$jar_path")"
  cp "$app_yml" ./application.yml 2>/dev/null || true
  java -Dfile.encoding=UTF-8 -jar "$jar_path" \
    --spring.config.location=file:./application.yml \
    --spring.datasource.druid.url="jdbc:mysql://localhost:3306/litemall?useUnicode=true&characterEncoding=UTF-8&serverTimezone=UTC&allowPublicKeyRetrieval=true&verifyServerCertificate=false&useSSL=false" \
    > "$output_dir/app_stdout.log" 2> "$output_dir/app_stderr.log" &
  app_pid=$!
  for i in $(seq 1 24); do
    sleep 5
    if curl -sf http://localhost:8080/wx/auth/info >/dev/null 2>&1 || \
      curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/wx/home/index 2>/dev/null | grep -qE "200|401|500"; then
      app_started=true
      echo "App started after ~$((i*5))s"
      break
    fi
    kill -0 "$app_pid" 2>/dev/null || { echo "App exited prematurely"; break; }
  done
fi

echo "=== Phase 3: Integration Tests ==="
if [[ "$app_started" == true ]]; then
  python3 "$deterministic_dir/integration.py" "$workspace" "$output_dir" || echo "Integration crashed"
else
  echo "Skipping: app not running"
  python3 - "$output_dir/integration_results.json" <<'PY'
import json
import sys

rubrics = [
    ("integ.app_boot", "应用构建启动"),
    ("integ.order_flow_intact", "下单流程正常"),
    ("integ.prepay_form", "prepay 返回支付宝表单"),
    ("integ.prepay_gateway_url", "表单指向支付宝网关"),
    ("integ.prepay_product_code", "产品码正确"),
    ("integ.prepay_order_binding", "prepay 绑定真实订单"),
    ("integ.prepay_does_not_mark_paid", "prepay 不提前履约"),
    ("integ.notify_endpoint_exists", "notify 端点存在"),
    ("integ.notify_processes_success", "notify 处理成功"),
    ("integ.notify_updates_only_target", "notify 只更新对应订单"),
    ("integ.logic_api", "使用正确的支付宝 API (page.pay)"),
]
results = [
    {"id": rid, "name": name, "dimension": "functionality", "type": "integration",
     "passed": False, "score": 0, "max_score": 1, "message": "应用未启动"}
    for rid, name in rubrics
]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
PY
fi

echo "=== Phase 4: E2E Tests ==="
if [[ "$app_started" == true ]]; then
  python3 "$deterministic_dir/e2e.py" "$workspace" "$output_dir" 2>&1 || echo "E2E crashed"
else
  echo "Skipping"
  python3 - "$output_dir/e2e_results.json" <<'PY'
import json
import sys
json.dump([
    {"id": "E1", "name": "Payment page shows Alipay option", "passed": False, "message": "应用未启动"},
    {"id": "E2", "name": "Alipay payment redirect", "passed": False, "message": "应用未启动"},
], open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
fi

echo "=== Phase 5: LLM Code Review ==="
python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$output_dir" || echo "LLM judge crashed"
