from typing import Any, Dict


def validate_result_contract(result: Dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    score = result.get("score")
    max_score = result.get("max_score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
        raise ValueError("score must be a normalized number between 0 and 1")
    if float(max_score) != 1.0:
        raise ValueError("max_score must be 1.0")
    if not isinstance(result.get("summary"), str):
        raise ValueError("summary must be a string")
    if not isinstance(result.get("rubrics", []), list):
        raise ValueError("rubrics must be a list")
    if not isinstance(result.get("agent", {}), dict):
        raise ValueError("agent must be an object")
    if not isinstance(result.get("metadata", {}), dict):
        raise ValueError("metadata must be an object")


def build_fallback_result(reason: str) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "score": 0.0,
        "max_score": 1.0,
        "summary": f"infra failure: {reason}",
        "rubrics": [
            {
                "id": "infra.result_missing",
                "name": "Result generation failed",
                "type": "deterministic",
                "passed": False,
                "score": 0,
                "max_score": 1,
                "message": reason,
                "infra_failure": True,
            }
        ],
        "agent": {"usage_available": False},
        "metadata": {
            "retryable_infra_failure": True,
            "infra_failure_kind": "result_contract",
            "infra_failure_message": reason,
        },
    }
