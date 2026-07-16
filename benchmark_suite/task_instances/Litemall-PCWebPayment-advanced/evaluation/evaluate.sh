#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
output_dir="${OUTPUT_DIR:-/output}"
workspace="${WORKSPACE:-/workspace}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
deterministic_dir="$task_instance_dir/evaluation/deterministic"
llm_assisted_dir="$task_instance_dir/evaluation/llm_assisted"
support_dir="$deterministic_dir/support"
keys_dir="$output_dir/alipay_keys"
mock_port=19876
mock_log="$output_dir/mock_gateway_requests.jsonl"
mock_pid=""
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
export PYTHONPATH="$support_dir:${PYTHONPATH:-}"

cleanup() {
  [[ -n "${mock_pid:-}" ]] && kill "$mock_pid" 2>/dev/null || true
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

echo "=== Phase 1.5: Load Fixed Keys & Start Mock Gateway ==="
rm -rf "$keys_dir"
sandbox_keys_file="${ALIPAY_SANDBOX_KEYS_FILE:-$workspace/alipay-sandbox-keys.json}"
if [[ ! -s "$sandbox_keys_file" ]]; then
  echo "INFRA: missing alipay sandbox runtime input at $sandbox_keys_file"
  exit 0
fi
if [[ "$sandbox_keys_file" != "$workspace/alipay-sandbox-keys.json" ]]; then
  cp "$sandbox_keys_file" "$workspace/alipay-sandbox-keys.json"
fi
python3 "$support_dir/sign_utils.py" fixture "$keys_dir" "$workspace"

mock_gateway_url="http://localhost:$mock_port/gateway.do"
alipay_app_id_value="$(cat "$keys_dir/app_id.txt" 2>/dev/null)"
alipay_seller_id_value="$(cat "$keys_dir/seller_id.txt" 2>/dev/null)"
alipay_merchant_private_b64="$(cat "$keys_dir/merchant_private_b64.txt" 2>/dev/null)"
alipay_public_b64="$(cat "$keys_dir/alipay_public_b64.txt" 2>/dev/null)"

export ALIPAY_APP_ID="$alipay_app_id_value"
export APP_ID="$alipay_app_id_value"
export ALIPAY_SELLER_ID="$alipay_seller_id_value"
export ALIPAY_PRIVATE_KEY="$alipay_merchant_private_b64"
export ALIPAY_APP_PRIVATE_KEY="$alipay_merchant_private_b64"
export APP_PRIVATE_KEY="$alipay_merchant_private_b64"
export ALIPAY_PUBLIC_KEY="$alipay_public_b64"
export ALIPAY_ALIPAY_PUBLIC_KEY="$alipay_public_b64"
export APP_PUBLIC_KEY="$alipay_public_b64"
export ALIPAY_SIGN_TYPE="RSA2"
export ALIPAY_GATEWAY_URL="$mock_gateway_url"
export ALIPAY_GATEWAY="$mock_gateway_url"
export ALIPAY_SERVER_URL="$mock_gateway_url"
export GATEWAY_URL="$mock_gateway_url"
export ALIPAY_NOTIFY_URL="http://127.0.0.1:8080/wx/order/alipay-notify"
export ALIPAY_RETURN_URL="http://127.0.0.1:8080/vue/index.html#/order/order-list"
export LITEMALL_WX_NOTIFY_URL="${LITEMALL_WX_NOTIFY_URL:-$ALIPAY_NOTIFY_URL}"
export LITEMALL_STORAGE_PUBLIC_URL="${LITEMALL_STORAGE_PUBLIC_URL:-http://127.0.0.1:8080/wx/storage/fetch/}"
export MOCK_LOG_FILE="$mock_log"

python3 "$support_dir/mock_alipay_gateway.py" \
  --keys-dir "$keys_dir" --port "$mock_port" --log-file "$mock_log" &
mock_pid=$!
sleep 2
if curl -sf "http://localhost:$mock_port/health" >/dev/null 2>&1; then
  echo "Mock gateway started (PID $mock_pid)"
else
  echo "WARNING: Mock gateway failed to start"
  mock_pid=""
fi

app_yml="$workspace/docker/litemall/application.yml"
if [[ -n "$alipay_app_id_value" && -n "$alipay_merchant_private_b64" && -n "$alipay_public_b64" ]]; then
  python3 - "$workspace" "$alipay_app_id_value" "$alipay_seller_id_value" "$alipay_merchant_private_b64" "$alipay_public_b64" "$mock_gateway_url" <<'PYPATCH'
import os
import re
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
app_id, seller_id, private_key, public_key, gateway_url = sys.argv[2:7]

mapping = {
    "app-id": app_id,
    "appId": app_id,
    "app_id": app_id,
    "private-key": private_key,
    "privateKey": private_key,
    "private_key": private_key,
    "alipay-public-key": public_key,
    "alipayPublicKey": public_key,
    "alipay_public_key": public_key,
    "public-key": public_key,
    "gateway-url": gateway_url,
    "gatewayUrl": gateway_url,
    "gateway_url": gateway_url,
    "gateway": gateway_url,
    "notify-url": os.environ["ALIPAY_NOTIFY_URL"],
    "notifyUrl": os.environ["ALIPAY_NOTIFY_URL"],
    "notify_url": os.environ["ALIPAY_NOTIFY_URL"],
    "return-url": os.environ["ALIPAY_RETURN_URL"],
    "returnUrl": os.environ["ALIPAY_RETURN_URL"],
    "return_url": os.environ["ALIPAY_RETURN_URL"],
}
if seller_id:
    mapping.update({"seller-id": seller_id, "sellerId": seller_id, "seller_id": seller_id})


def patch_yml(path):
    content = path.read_text(encoding="utf-8", errors="replace")
    out = []
    in_alipay = False
    alipay_indent = None
    for line in content.splitlines():
        m = re.match(r'^(\s*)alipay\s*:\s*(?:#.*)?$', line)
        if m:
            in_alipay = True
            alipay_indent = len(m.group(1))
            out.append(line)
            continue
        if in_alipay:
            indent = len(line) - len(line.lstrip(" "))
            if line.strip() and indent <= alipay_indent:
                in_alipay = False
                alipay_indent = None
            else:
                km = re.match(r'^(\s*)([A-Za-z0-9_-]+)\s*:\s*.*$', line)
                if km and km.group(2) in mapping:
                    line = f"{km.group(1)}{km.group(2)}: {mapping[km.group(2)]}"
        out.append(line)
    patched = "\n".join(out) + "\n"
    patched = re.sub(r'https://openapi[a-z.-]*\.alipay[a-z.]*\.com/gateway\.do', gateway_url, patched)
    path.write_text(patched, encoding="utf-8")
    print(f"Patched fixed mock Alipay config in {path.relative_to(workspace)}")


def patch_known_runtime_urls(path):
    content = path.read_text(encoding="utf-8", errors="replace")
    replacements = {
        "jdbc:mysql://mysql:3306/litemall": "jdbc:mysql://localhost:3306/litemall",
    }
    patched = content
    for old, new in replacements.items():
        patched = patched.replace(old, new)
    out = []
    key_overrides = {
        "notify-url": os.environ["LITEMALL_WX_NOTIFY_URL"],
        "return-url": os.environ["ALIPAY_RETURN_URL"],
        "address": os.environ["LITEMALL_STORAGE_PUBLIC_URL"],
    }
    for line in patched.splitlines():
        match = re.match(r"^(\s*)(notify-url|return-url|address)\s*:\s*(.*)$", line)
        if match:
            key = match.group(2)
            value = match.group(3).strip()
            if key == "address" and "/wx/storage/fetch" not in value:
                out.append(line)
                continue
            out.append(f"{match.group(1)}{key}: {key_overrides[key]}")
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Patched runtime-local URLs/DB in {path.relative_to(workspace)}")


targets = [
    workspace / "docker/litemall/application.yml",
    workspace / "litemall-core/src/main/resources/application-core.yml",
]
seen = set()
for target in targets:
    if target in seen or not target.exists():
        continue
    seen.add(target)
    patch_yml(target)
    patch_known_runtime_urls(target)
PYPATCH
fi

echo "=== Phase 2: Build & Start Application ==="
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
  if [[ -f "$sql_file" ]]; then
    echo "Importing: $(basename "$sql_file")"
    sudo mysql -u root litemall < "$sql_file" 2>&1 | tail -3
  fi
done

python3 - "$workspace" <<'PYDBPATCH'
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
for rel in [
    "docker/litemall/application.yml",
    "litemall-core/src/main/resources/application-core.yml",
]:
    path = workspace / rel
    if not path.exists():
        continue
    content = path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("jdbc:mysql://mysql:3306/litemall", "jdbc:mysql://localhost:3306/litemall")
    path.write_text(content, encoding="utf-8")
    print(f"Patched DB host in {rel}")
PYDBPATCH

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
  python3 "$deterministic_dir/integration.py" "$workspace" "$output_dir" "$keys_dir" || echo "Integration crashed"
else
  echo "Skipping: app not running"
  python3 - "$output_dir/integration_results.json" <<'PY'
import json
import sys

items = [
    ("integ.app_boot", "应用构建启动", "functionality"),
    ("integ.prepay_form", "prepay 返回支付宝表单", "functionality"),
    ("integ.prepay_hits_mock", "prepay 请求到达 mock 网关", "functionality"),
    ("integ.notify_rejects_unsigned", "无签名通知被拒", "security"),
    ("integ.notify_rejects_wrong_amount", "金额篡改通知被拒", "security"),
    ("integ.notify_rejects_wrong_appid", "app_id 篡改通知被拒", "security"),
    ("integ.notify_signed_success", "有效签名通知通过", "correctness"),
    ("integ.notify_idempotent", "通知幂等", "correctness"),
    ("integ.terminal_not_downgraded", "终态不被覆盖", "security"),
    ("integ.return_url_not_final", "return_url 不作终态", "security"),
    ("integ.query_endpoint", "查询端点存在", "functionality"),
    ("integ.refund_endpoint", "退款端点存在", "functionality"),
    ("integ.notify_wrong_order", "不存在订单号的通知被拒", "security"),
    ("integ.prepay_out_trade_no_matches", "prepay 使用真实订单号", "correctness"),
    ("integ.refund_idempotent", "退款幂等 (out_request_no)", "correctness"),
    ("integ.refund_partial_sequence", "部分退款请求号与金额", "correctness"),
    ("integ.refund_over_amount_rejected", "超额退款被拒", "security"),
    ("integ.refund_cumulative_over_amount_rejected", "累计超额退款被拒", "security"),
    ("integ.refund_fund_change_n_not_final", "fund_change=N 不作为最终退款", "security"),
    ("integ.query_unknown_not_paid", "查询未知/待支付不入账", "security"),
    ("integ.paid_order_close_rejected", "已支付订单不能关单", "security"),
    ("integ.close_failure_not_cancelled", "关单失败不取消本地订单", "security"),
    ("integ.close_endpoint", "关单端点存在", "functionality"),
]
results = [
    {"id": rid, "name": name, "dimension": dim, "type": "integration",
     "passed": False, "score": 0, "max_score": 1, "message": "应用未启动"}
    for rid, name, dim in items
]
json.dump(results, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
fi

echo "=== Phase 4: E2E Tests ==="
if [[ "$app_started" == true ]]; then
  python3 "$deterministic_dir/e2e.py" "$workspace" "$output_dir" 2>&1 || echo "E2E crashed"
else
  echo "Skipping: app not running"
  python3 - "$output_dir/e2e_results.json" <<'PY'
import json
import sys
json.dump([
    {"id": "E1", "name": "前端支付宝选项", "passed": False, "message": "应用未启动"},
    {"id": "E2", "name": "支付跳转", "passed": False, "message": "应用未启动"},
], open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
fi

echo "=== Phase 5: LLM Code Review ==="
python3 "$llm_assisted_dir/run_llm_assisted.py" "$workspace" "$output_dir" || echo "LLM judge crashed"
