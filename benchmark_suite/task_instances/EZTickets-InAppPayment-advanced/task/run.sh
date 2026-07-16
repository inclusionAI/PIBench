#!/usr/bin/env bash
set -uo pipefail

task_instance_dir="${TASK_INSTANCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
workspace="${WORKSPACE:-/workspace}"
output_dir="${OUTPUT_DIR:-/output}"
artifacts_dir="${PAYSKILLS_ARTIFACTS_DIR:-$output_dir/artifacts}"
mode="${AGENT_MODE:-${PAYSKILLS_MODE:-no-skill}}"
agent_type="${AGENT_TYPE:-claude-code}"
model="${AGENT_MODEL:-}"

task_instance_name_from_toml() {
  sed -n 's/^name *= *"\([^"]*\)".*/\1/p' "$task_instance_dir/task_instance.toml" 2>/dev/null | head -1
}

task_instance_toml_name="$(task_instance_name_from_toml || true)"
case_name="${CASE_NAME:-${PAYSKILLS_CASE_NAME:-${task_instance_toml_name:-$(basename "$task_instance_dir")}}}"

export WORKSPACE="$workspace"
export WORKDIR="$workspace"
export CASE_NAME="$case_name"
export PAYSKILLS_CASE_NAME="${PAYSKILLS_CASE_NAME:-$case_name}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$artifacts_dir/claude_config}"

mkdir -p "$workspace" "$output_dir" "$artifacts_dir" "$CLAUDE_CONFIG_DIR"

if [[ ! -d "$workspace/ez_tickets_backend" && -d "$task_instance_dir/task/fixtures/project" ]]; then
  cp -a --no-preserve=ownership "$task_instance_dir/task/fixtures/project/." "$workspace/"
fi
chmod +x "$workspace/start.sh" 2>/dev/null || true
rm -rf "$workspace/ez_tickets_backend/node_modules"

runtime_turns="$artifacts_dir/turns.runtime.json"
python3 - "$task_instance_dir/task/turns.json" "$runtime_turns" "$mode" <<'PY'
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
    prefix = (
        "已确认同意使用支付宝支付集成 Skill 的服务声明。当前是自动化 benchmark，"
        "请不要停在确认、澄清或等待用户回复步骤，直接完成代码修改、验证并输出结果。"
    )
    turns[0]["user"] = prefix + "\n\n" + str(turns[0].get("user") or "")
target.write_text(json.dumps({"turns": turns}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

cd "$workspace"

payskills-agent drive-turns \
  --agent-type "$agent_type" \
  --model "$model" \
  --mode "$mode" \
  --instruction "$task_instance_dir/task/instruction.md" \
  --turns "$runtime_turns" \
  --skills "$task_instance_dir/task/skills" \
  --workspace "$workspace" \
  --output-dir "$artifacts_dir" \
  --task-instance-dir "$task_instance_dir" \
  --home "$artifacts_dir/agent-home" \
  --timeout "${AGENT_TIMEOUT:-3600}" \
  --max-turns "${AGENT_MAX_TURNS:-500}" \
  --skill-trigger "${PAYSKILLS_SKILL_TRIGGER:-}" \
  --skill-name "${PAYSKILLS_SKILL_NAME:-alipay-payment-integration}"
agent_rc=$?

if [[ "$agent_rc" -ne 0 ]]; then
  {
    echo "AGENT NON-ZERO EXIT: agent_type=$agent_type exit_code=$agent_rc"
    echo "time=$(date -u +%FT%TZ)"
    echo "--- stderr tail ---"
    find "$artifacts_dir/turns" -name raw_stderr.txt -print -exec tail -n 80 {} \; 2>/dev/null
  } >> "$output_dir/run_error.log"
  if grep -qiE "rate limit|429|402|insufficient|overloaded|authentication|invalid api key|ENOTFOUND|ECONNREFUSED|timeout" \
    "$artifacts_dir"/turns/*/raw_stderr.txt "$artifacts_dir"/turns/*/raw_stdout.txt 2>/dev/null; then
    touch "$output_dir/.infra_failure_agent"
  fi
fi

exit 0
