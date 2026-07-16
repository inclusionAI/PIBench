#!/usr/bin/env bash
# Prepare the Gymie workspace, real-sandbox forwarding proxy and credentials, then run the agent.
set -uo pipefail

TASK_INSTANCE_DIR="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CASE_DIR="$TASK_INSTANCE_DIR/task"
SUPPORT_DIR="$TASK_INSTANCE_DIR/evaluation/deterministic/support"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
WORKSPACE="${WORKSPACE:-/workspace}"
AGENT_TYPE="${AGENT_TYPE:-claude-code}"
AGENT_MODEL="${AGENT_MODEL:-}"
AGENT_MODE="${AGENT_MODE:-}"
ARTIFACTS_DIR="${PAYSKILLS_ARTIFACTS_DIR:-$OUTPUT_DIR/artifacts}"
KEY_DIR="$OUTPUT_DIR/real-alipay-keys"
PROXY_PORT="${ALIPAY_PROXY_PORT:-8233}"
RUN_FINGERPRINT="$(printf '%s:%s' "$OUTPUT_DIR" "$WORKSPACE" | sha1sum | cut -c1-6)"
APP_PORT="${APP_PORT:-$((18000 + 16#$RUN_FINGERPRINT % 20000))}"
APP_BASE_URL="http://127.0.0.1:${APP_PORT}"

export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$ARTIFACTS_DIR/claude_config}"
mkdir -p "$OUTPUT_DIR" "$ARTIFACTS_DIR" "$CLAUDE_CONFIG_DIR"
RUN_LOG="$OUTPUT_DIR/run_sh.log"
exec > >(tee -a "$RUN_LOG") 2>&1
echo "=== run.sh start $(date -Is) agent_type=$AGENT_TYPE ==="

fail_infra() {
    local reason="$1"
    echo "INFRA FAILURE: $reason"
    echo "{\"agent_type\":\"$AGENT_TYPE\",\"reason\":\"$reason\",\"stage\":\"run.sh\"}" \
        > "$OUTPUT_DIR/infra_failure.json"
    echo "$reason" >> "$OUTPUT_DIR/run_error.log"
}

write_key_file() {
    local dest="$1"
    local inline="$2"
    local src="$3"
    mkdir -p "$(dirname "$dest")"
    if [[ -n "$inline" ]]; then
        printf '%s\n' "$inline" > "$dest"
        chmod 600 "$dest"
        return 0
    fi
    if [[ -n "$src" && -f "$src" ]]; then
        cp "$src" "$dest"
        chmod 600 "$dest"
        return 0
    fi
    return 1
}

load_sandbox_keys_json() {
    local json_path="$1"
    [[ -f "$json_path" ]] || return 1
    python3 - "$json_path" "$KEY_DIR" > "$OUTPUT_DIR/sandbox_env.sh" <<'PYJSON'
import json
import shlex
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
key_dir = Path(sys.argv[2])
data = json.loads(json_path.read_text(encoding="utf-8"))
key_dir.mkdir(parents=True, exist_ok=True)

def pem_block(label, body):
    body = "".join(str(body or "").strip().split())
    lines = [body[i:i+64] for i in range(0, len(body), 64)]
    return "-----BEGIN %s-----\n%s\n-----END %s-----\n" % (label, "\n".join(lines), label)

app_private_body = data.get("merchant_private_key_pkcs1") or data.get("merchant_private_key_pkcs8")
if not app_private_body:
    raise SystemExit("merchant_private_key_pkcs1/pkcs8 missing")
private_label = "RSA PRIVATE KEY" if data.get("merchant_private_key_pkcs1") else "PRIVATE KEY"
(key_dir / "app_private_key.pem").write_text(pem_block(private_label, app_private_body), encoding="utf-8")

if data.get("alipay_public_key"):
    (key_dir / "real_alipay_public_key.pem").write_text(
        pem_block("PUBLIC KEY", data["alipay_public_key"]), encoding="utf-8")

buyer = data.get("sandbox_buyer") or {}
buyer_id = buyer.get("buyer_id") or buyer.get("user_id") or buyer.get("id") or ""
buyer_logon_id = buyer.get("buyer_logon_id") or buyer.get("account") or buyer.get("login_id") or ""
values = {
    "REAL_ALIPAY_GATEWAY_URL": data.get("gateway") or "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
    "ALIPAY_APP_ID": data.get("app_id") or "",
    "ALIPAY_SELLER_ID": data.get("seller_id") or "",
    "ALIPAY_MINIAPP_APP_ID": data.get("miniapp_app_id") or data.get("op_app_id") or data.get("app_id") or "",
    "ALIPAY_SANDBOX_BUYER_ID": buyer_id,
    "ALIPAY_SANDBOX_BUYER_LOGON_ID": buyer_logon_id,
}
for key, value in values.items():
    print("export %s=%s" % (key, shlex.quote(str(value))))
PYJSON
    # shellcheck disable=SC1090
    source "$OUTPUT_DIR/sandbox_env.sh"
    return 0
}

# ---- 1. real sandbox app credential + mock callback/signature keypair -------
python3 "$SUPPORT_DIR/gen_keys.py" "$KEY_DIR" || { fail_infra "mock callback RSA key generation failed"; exit 0; }
SANDBOX_KEYS_JSON="${ALIPAY_SANDBOX_KEYS_FILE:-${REAL_ALIPAY_KEYS_JSON:-${ALIPAY_SANDBOX_KEYS_JSON:-}}}"
if [[ -f "$SANDBOX_KEYS_JSON" ]]; then
    load_sandbox_keys_json "$SANDBOX_KEYS_JSON" \
        || { fail_infra "failed to load sandbox keys json: $SANDBOX_KEYS_JSON"; exit 0; }
fi
export REAL_ALIPAY_GATEWAY_URL="${REAL_ALIPAY_GATEWAY_URL:-${ALIPAY_REAL_GATEWAY_URL:-https://openapi-sandbox.dl.alipaydev.com/gateway.do}}"
export ALIPAY_APP_ID="${REAL_ALIPAY_APP_ID:-${ALIPAY_APP_ID:-}}"
export ALIPAY_SELLER_ID="${REAL_ALIPAY_SELLER_ID:-${ALIPAY_SELLER_ID:-}}"
export ALIPAY_MINIAPP_APP_ID="${REAL_ALIPAY_MINIAPP_APP_ID:-${ALIPAY_MINIAPP_APP_ID:-${ALIPAY_APP_ID:-}}}"
export ALIPAY_SANDBOX_BUYER_ID="${REAL_ALIPAY_SANDBOX_BUYER_ID:-${ALIPAY_SANDBOX_BUYER_ID:-}}"
export ALIPAY_SANDBOX_BUYER_LOGON_ID="${REAL_ALIPAY_SANDBOX_BUYER_LOGON_ID:-${ALIPAY_SANDBOX_BUYER_LOGON_ID:-}}"
export GATEWAY_LOG="$OUTPUT_DIR/gateway_requests.jsonl"
export ALIPAY_KEY_DIR="$KEY_DIR"
export ALIPAY_PROXY_PORT="$PROXY_PORT"

if [[ -z "$ALIPAY_APP_ID" ]]; then
    fail_infra "REAL_ALIPAY_APP_ID/ALIPAY_APP_ID is required for real sandbox mode"
    exit 0
fi
if [[ -z "$ALIPAY_MINIAPP_APP_ID" ]]; then
    fail_infra "REAL_ALIPAY_MINIAPP_APP_ID/ALIPAY_MINIAPP_APP_ID is required for JSAPI op_app_id checks"
    exit 0
fi

APP_PRIVATE_SRC="${REAL_ALIPAY_APP_PRIVATE_KEY_PATH:-${ALIPAY_APP_PRIVATE_KEY_PATH:-}}"
APP_PRIVATE_INLINE="${REAL_ALIPAY_APP_PRIVATE_KEY:-${ALIPAY_APP_PRIVATE_KEY:-}}"

if [[ ! -f "$KEY_DIR/app_private_key.pem" ]]; then
    write_key_file "$KEY_DIR/app_private_key.pem" "$APP_PRIVATE_INLINE" "$APP_PRIVATE_SRC" \
        || { fail_infra "real sandbox app private key missing; set REAL_ALIPAY_KEYS_JSON/ALIPAY_SANDBOX_KEYS_JSON, REAL_ALIPAY_APP_PRIVATE_KEY_PATH, or REAL_ALIPAY_APP_PRIVATE_KEY"; exit 0; }
fi
if ! curl -fsS "http://127.0.0.1:${PROXY_PORT}/__health" >/dev/null 2>&1; then
    nohup python3 "$SUPPORT_DIR/real_sandbox_proxy.py" > "$OUTPUT_DIR/real_sandbox_proxy.log" 2>&1 &
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        curl -fsS "http://127.0.0.1:${PROXY_PORT}/__health" >/dev/null 2>&1 && break
    done
fi
if ! curl -fsS "http://127.0.0.1:${PROXY_PORT}/__health" >/dev/null 2>&1; then
    fail_infra "real sandbox forwarding proxy failed to start (see real_sandbox_proxy.log)"
    exit 0
fi
echo "real sandbox proxy ready on 127.0.0.1:${PROXY_PORT}, upstream=$REAL_ALIPAY_GATEWAY_URL"

# ---- 2. agent workspace ---------------------------------------------------
if [[ ! -d "$WORKSPACE" ]]; then
    fail_infra "workspace missing: $WORKSPACE"
    exit 0
fi
cd "$WORKSPACE"

if [[ ! -f artisan || ! -f composer.json || ! -f package.json ]]; then
    fail_infra "workspace fixture is incomplete: $WORKSPACE"
    exit 0
fi

if [[ ! -f .env.example ]]; then
    fail_infra ".env.example missing from fixture project"
    exit 0
fi
cp .env.example .env
python3 "$SUPPORT_DIR/update_env.py" .env \
    "APP_NAME=Gymie Membership Checkout" \
    "APP_ENV=local" \
    "APP_DEBUG=true" \
    "APP_URL=$APP_BASE_URL" \
    "DB_CONNECTION=sqlite" \
    "DB_DATABASE=$WORKSPACE/storage/app/database.sqlite" \
    "SESSION_DRIVER=file" \
    "CACHE_STORE=file" \
    "QUEUE_CONNECTION=sync" \
    "MAIL_MAILER=log" \
    "ALIPAY_GATEWAY_URL=http://127.0.0.1:${PROXY_PORT}/gateway.do" \
    "ALIPAY_APP_ID=$ALIPAY_APP_ID" \
    "ALIPAY_SELLER_ID=$ALIPAY_SELLER_ID" \
    "ALIPAY_MINIAPP_APP_ID=$ALIPAY_MINIAPP_APP_ID" \
    "ALIPAY_APP_PRIVATE_KEY_PATH=$KEY_DIR/app_private_key.pem" \
    "ALIPAY_ALIPAY_PUBLIC_KEY_PATH=$KEY_DIR/alipay_public_key.pem" \
    "ALIPAY_NOTIFY_URL=$APP_BASE_URL/membership-checkout/notify" \
    "ALIPAY_SANDBOX_BUYER_ID=$ALIPAY_SANDBOX_BUYER_ID" \
    "ALIPAY_SANDBOX_BUYER_LOGON_ID=$ALIPAY_SANDBOX_BUYER_LOGON_ID"

composer install --prefer-dist --no-interaction --no-progress --no-scripts >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "composer install failed (see laravel_setup.log)"; exit 0; }
composer dump-autoload --optimize --no-scripts >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "composer dump-autoload failed (see laravel_setup.log)"; exit 0; }
npm ci >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "npm ci failed (see laravel_setup.log)"; exit 0; }
npm run build >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "npm run build failed (see laravel_setup.log)"; exit 0; }

mkdir -p storage/app storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache
touch storage/app/database.sqlite

php artisan package:discover --ansi >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "php artisan package:discover failed (see laravel_setup.log)"; exit 0; }
php artisan key:generate --force --ansi >> "$OUTPUT_DIR/laravel_setup.log" 2>&1
php -d memory_limit=512M artisan migrate:fresh --seed --force --ansi >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || { fail_infra "baseline migrate:fresh --seed failed (see laravel_setup.log)"; exit 0; }
php artisan shield:generate --all --panel=admin --ansi >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 \
    || echo "warning: shield:generate failed (non-fatal)"

payskills-diff init --workspace "$WORKSPACE" \
    || { fail_infra "workspace baseline reset failed"; exit 0; }
echo "workspace ready at $WORKSPACE app_base_url=$APP_BASE_URL proxy_port=$PROXY_PORT"

apply_skill_prefix() {
    local body="$1"
    if [[ "${AGENT_MODE:-}" == "with-skill" && "${INJECT_SKILL_NAME:-false}" == "true" && -d "$TASK_INSTANCE_DIR/task/skills" ]]; then
        local skill_name
        skill_name="$(ls "$TASK_INSTANCE_DIR/task/skills" 2>/dev/null | head -1)"
        if [[ -n "$skill_name" ]]; then
            printf '/%s\n\n已确认同意使用支付宝支付集成 Skill 的服务声明。当前是自动化 benchmark，请不要停在确认、澄清或等待用户回复步骤，直接完成代码修改、验证并输出结果。\n\n%s' "$skill_name" "$body"
            return 0
        fi
    fi
    printf '%s' "$body"
}

# ---- 3. agent input -------------------------------------------------------
apply_skill_prefix "$(cat "$TASK_INSTANCE_DIR/task/instruction.md")" > "$OUTPUT_DIR/agent_input.txt"

# ---- 4. run the agent -----------------------------------------------------
export WORKSPACE
runtime_turns="$ARTIFACTS_DIR/turns.runtime.json"
python3 - "$TASK_INSTANCE_DIR/task/turns.json" "$runtime_turns" "$AGENT_MODE" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
mode = sys.argv[3]
payload = json.loads(source.read_text(encoding="utf-8"))
turns = payload.get("turns") if isinstance(payload, dict) else payload
if not isinstance(turns, list) or not turns:
    raise SystemExit("turns.json must contain at least one turn")
turns = [dict(turn) for turn in turns]
if mode == "with-skill":
    turns[0]["user"] = (
        "已确认同意使用支付宝支付集成 Skill 的服务声明。当前是自动化 benchmark，"
        "请不要停在确认、澄清或等待用户回复步骤，直接完成代码修改、验证并输出结果。"
        "\n\n" + str(turns[0].get("user") or "")
    )
target.write_text(json.dumps({"turns": turns}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

payskills-agent drive-turns \
  --agent-type "$AGENT_TYPE" \
  --model "$AGENT_MODEL" \
  --mode "${AGENT_MODE:-no-skill}" \
  --instruction "$TASK_INSTANCE_DIR/task/instruction.md" \
  --turns "$runtime_turns" \
  --skills "$TASK_INSTANCE_DIR/task/skills" \
  --workspace "$WORKSPACE" \
  --output-dir "$ARTIFACTS_DIR" \
  --task-instance-dir "$TASK_INSTANCE_DIR" \
  --home "$ARTIFACTS_DIR/agent-home" \
  --timeout "${AGENT_TIMEOUT:-3600}" \
  --max-turns "${AGENT_MAX_TURNS:-500}" \
  --skill-trigger "${PAYSKILLS_SKILL_TRIGGER:-}" \
  --skill-name "${PAYSKILLS_SKILL_NAME:-alipay-payment-integration}"
AGENT_RC=$?
echo "$AGENT_RC" > "$OUTPUT_DIR/.agent_rc"

echo "agent exit code: $AGENT_RC"
echo "=== run.sh done $(date -Is) ==="
exit 0
