#!/usr/bin/env bash
set -uo pipefail
TASK_INSTANCE_DIR="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CASE_DIR="$TASK_INSTANCE_DIR/task"
SUPPORT_DIR="$TASK_INSTANCE_DIR/evaluation/deterministic/support"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
PROJECT_DIR="${WORKSPACE:-/workspace}"
AGENT_TYPE="${AGENT_TYPE:-claude-code}"
AGENT_MODEL="${AGENT_MODEL:-}"
AGENT_MODE="${AGENT_MODE:-}"
ARTIFACTS_DIR="${PAYSKILLS_ARTIFACTS_DIR:-$OUTPUT_DIR/artifacts}"
KEY_DIR="${ALIPAY_KEY_DIR:-$OUTPUT_DIR/alipay-keys}"
GATEWAY_PORT="${GATEWAY_PORT:-8234}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$ARTIFACTS_DIR/claude_config}"
mkdir -p "$OUTPUT_DIR" "$ARTIFACTS_DIR" "$CLAUDE_CONFIG_DIR"
exec > >(tee -a "$OUTPUT_DIR/run.log") 2>&1
echo "=== run.sh start $(date -Is) agent=$AGENT_TYPE model=$AGENT_MODEL ==="
python3 "$SUPPORT_DIR/gen_keys.py" "$KEY_DIR" || echo "key generation failed; tests will report if gateway cannot run"
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
if ! curl -fsS "http://127.0.0.1:${GATEWAY_PORT}/admin/trades" >/dev/null 2>&1; then
    echo "mock alipay gateway failed to start; tests will report" >> "$OUTPUT_DIR/run.log"
else
    echo "mock alipay gateway ready on 127.0.0.1:${GATEWAY_PORT}"
fi
if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "workspace missing: $PROJECT_DIR" | tee "$OUTPUT_DIR/run_error.log"
  exit 0
fi
if [[ ! -f "$PROJECT_DIR/artisan" || ! -f "$PROJECT_DIR/composer.json" ]]; then
  echo "workspace fixture is incomplete: $PROJECT_DIR" | tee "$OUTPUT_DIR/run_error.log"
  exit 0
fi
rm -f "$PROJECT_DIR/BENCHMARK_ENVIRONMENT.md" "$PROJECT_DIR/scripts/check_environment.sh"
cd "$PROJECT_DIR"
if [[ -f .env.example ]]; then cp .env.example .env; else touch .env; fi
python3 - <<'PY' .env "$KEY_DIR" "$GATEWAY_PORT"
from pathlib import Path
import sys
p=Path(sys.argv[1]); key_dir=Path(sys.argv[2]); port=sys.argv[3]
lines=p.read_text(errors='ignore').splitlines() if p.exists() else []
def env_key(path):
    try:
        return path.read_text().strip().replace('\n', '\\n')
    except OSError:
        return ''
updates={
 'APP_ENV':'local','APP_DEBUG':'true','APP_URL':'http://127.0.0.1:8000','LOG_CHANNEL':'stderr',
 'DB_CONNECTION':'sqlite','DB_DATABASE':'/workspace/database/database.sqlite',
 'CACHE_STORE':'file','SESSION_DRIVER':'file','QUEUE_CONNECTION':'sync','MAIL_MAILER':'log',
 'ALIPAY_JSAPI_DEMO_MODE':'false',
 'ALIPAY_JSAPI_GATEWAY_URL':f'http://127.0.0.1:{port}/gateway',
 'ALIPAY_JSAPI_APP_ID':'2021003100000001','ALIPAY_JSAPI_MINI_APP_ID':'2021004100666666',
 'ALIPAY_JSAPI_SELLER_ID':'2088201111222233','ALIPAY_JSAPI_REFUND_TOKEN':'bench-refund-token',
 'ALIPAY_JSAPI_PRIVATE_KEY':env_key(key_dir/'app_private_key.pem'),
 'ALIPAY_JSAPI_PUBLIC_KEY':env_key(key_dir/'alipay_public_key.pem'),
 'ALIPAY_JSAPI_NOTIFY_URL':'http://127.0.0.1:8000/alipay-jsapi/notify'
}
seen=set(); out=[]
for line in lines:
    key=line.split('=',1)[0] if '=' in line else None
    if key in updates:
        out.append(f'{key}="{updates[key]}"' if '\\n' in updates[key] else f'{key}={updates[key]}'); seen.add(key)
    else: out.append(line)
for k,v in updates.items():
    if k not in seen: out.append(f'{k}="{v}"' if '\\n' in v else f'{k}={v}')
p.write_text('\n'.join(out)+'\n')
PY
mkdir -p database storage/app storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache
touch database/database.sqlite storage/app/database.sqlite
composer install --no-interaction --prefer-dist --no-progress > "$OUTPUT_DIR/composer_install.log" 2>&1 || echo "composer install failed; tests will report if app cannot run"
if [[ -f package.json ]]; then npm install --no-audit --no-fund > "$OUTPUT_DIR/npm_install.log" 2>&1 || echo "npm install failed (non-fatal for API tests)"; fi
php artisan key:generate --force --ansi >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 || true
php artisan config:clear >> "$OUTPUT_DIR/laravel_setup.log" 2>&1 || true
payskills-diff init --workspace "$PROJECT_DIR" \
  || { echo "workspace baseline reset failed" | tee "$OUTPUT_DIR/run_error.log"; exit 0; }
payskills-agent drive-turns \
  --agent-type "$AGENT_TYPE" \
  --model "$AGENT_MODEL" \
  --mode "${AGENT_MODE:-no-skill}" \
  --instruction "$TASK_INSTANCE_DIR/task/instruction.md" \
  --turns "$TASK_INSTANCE_DIR/task/turns.json" \
  --skills "$TASK_INSTANCE_DIR/task/skills" \
  --workspace "$PROJECT_DIR" \
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
