#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
out_dir=Path(sys.argv[1]); result_path=out_dir/"result.json"; case_name=sys.argv[2]
payload=json.loads(result_path.read_text(encoding="utf-8"))
metadata=payload.setdefault("metadata", {})
rubrics=payload.get("rubrics", [])
for item in rubrics:
    if item.get("test_infra_failure"):
        metadata["retryable_infra_failure"] = True
    if item.get("type") == "llm_assisted" and item.get("test_infra_failure"):
        metadata["llm_judge_infra_failure"] = True
scenario = os.environ.get("PAYSKILLS_SCENARIO", "")
if scenario not in ("basic", "advanced"):
    raise ValueError("unsupported BookCars evaluation scenario: %r" % scenario)
if scenario == "advanced":
    integration=[r for r in rubrics if str(r.get("id","")).startswith("I")]
    hard=[r for r in rubrics if str(r.get("id","")).startswith(("I","E"))]
    integration_infra=bool(integration) and all(r.get("test_infra_failure") for r in integration)
    hard_infra=bool(hard) and all(r.get("test_infra_failure") for r in hard)
    if integration_infra or hard_infra:
        metadata["runtime_infra_failure"] = True
        metadata["retryable_infra_failure"] = True
        metadata["raw_score_before_infra"] = payload.get("score")
        payload["score"] = 0.0
        payload["summary"] = str(payload.get("summary", "")) + "; runtime infra failure, rerun required"
payload["metadata"] = metadata
result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
