#!/usr/bin/env python3
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
artifacts_dir = Path(sys.argv[2])
result_path = out_dir / "result.json"
payload = json.loads(result_path.read_text(encoding="utf-8"))
patch_path = artifacts_dir / "patch.diff"
changed_path = artifacts_dir / "changed_files.txt"
agent_infra = (out_dir / ".infra_failure_agent").exists()
patch_empty = (not patch_path.exists()) or patch_path.stat().st_size == 0
changed_empty = (not changed_path.exists()) or changed_path.stat().st_size == 0
no_op = (not agent_infra) and patch_empty and changed_empty
metadata = payload.setdefault("metadata", {})
metadata.update({
    "patch_empty": patch_empty,
    "changed_files_empty": changed_empty,
    "no_op_submission": no_op,
    "agent_infra_failure": agent_infra,
})
if agent_infra or no_op:
    message = "agent 未启动（infra failure），不计分" if agent_infra else "agent 未产出代码改动（no-op submission），不计入 baseline 自然得分"
    for item in payload.get("rubrics", []):
        if item.get("weight", 0) > 0:
            item["passed"] = False
            item["score"] = 0.0
            item["weighted_score"] = 0.0
            item["message"] = message
    payload["score"] = 0.0
    payload["summary"] = message
    if agent_infra:
        metadata["retryable_infra_failure"] = True
payload["metadata"] = metadata
result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
