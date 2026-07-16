from typing import Any, Dict, Iterable, List, Optional, Tuple

from payskills_runtime.result.contract import build_fallback_result, validate_result_contract


CANONICAL_RUBRIC_TYPES = {"deterministic", "llm_assisted"}
LLM_ASSISTED_LEGACY_TYPES = {"llm", "llm_judge", "llm_review", "judge", "soft"}
DETERMINISTIC_LEGACY_TYPES = {"hard", "static", "integration", "e2e", "unit", "advisory"}


def rubric_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("rubrics", [])
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def float_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def safe_weight(value: Any) -> Tuple[float, Optional[str]]:
    if value is None:
        return 1.0, None
    weight = float_or_none(value)
    if weight is None or weight < 0:
        return 0.0, "invalid_weight"
    return weight, None


def safe_max_score(value: Any) -> Tuple[float, Optional[str]]:
    max_score = float_or_none(value if value is not None else 1)
    if max_score is None or max_score <= 0:
        return 1.0, "invalid_max_score"
    return max_score, None


def round_score(value: float) -> float:
    return round(float(value), 10)


def input_rubrics(input_payloads: Iterable[Any]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    errors: List[Dict[str, Any]] = []
    for payload_index, payload in enumerate(input_payloads):
        for rubric in rubric_list(payload):
            rubric_id = str(rubric.get("id") or "").strip()
            if not rubric_id:
                errors.append(
                    {
                        "rubric_id": "",
                        "source_index": payload_index,
                        "error": "missing_rubric_id",
                    }
                )
                continue
            if rubric_id in by_id:
                errors.append(
                    {
                        "rubric_id": rubric_id,
                        "source_index": payload_index,
                        "error": "duplicate_rubric_result_ignored",
                    }
                )
                continue
            by_id[rubric_id] = rubric
    return by_id, errors


def canonical_rubric_type(definition: Dict[str, Any], source: Dict[str, Any]) -> str:
    for payload in (definition, source):
        value = str(payload.get("type") or "").strip()
        if value in CANONICAL_RUBRIC_TYPES:
            return value
        if value in LLM_ASSISTED_LEGACY_TYPES:
            return "llm_assisted"
        if value in DETERMINISTIC_LEGACY_TYPES:
            return "deterministic"
    return "deterministic"


def compose_result(
    rubric_defs: Any,
    input_payloads: Iterable[Any],
    *,
    agent: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compose atomic rubric results into the final weighted result.json payload."""
    input_payloads = list(input_payloads)
    definitions = rubric_list(rubric_defs)
    result_by_id, compose_errors = input_rubrics(input_payloads)

    rubrics: List[Dict[str, Any]] = []
    missing_rubrics: List[str] = []
    definition_ids = []
    weighted_total = 0.0
    weight_sum = 0.0
    raw_score = 0.0
    raw_max_score = 0.0

    for index, definition in enumerate(definitions):
        rubric_id = str(definition.get("id") or "").strip()
        if not rubric_id:
            compose_errors.append(
                {
                    "rubric_id": "",
                    "definition_index": index,
                    "error": "missing_rubric_id_in_definition",
                }
            )
            continue
        if rubric_id in definition_ids:
            compose_errors.append(
                {
                    "rubric_id": rubric_id,
                    "definition_index": index,
                    "error": "duplicate_rubric_definition_ignored",
                }
            )
            continue
        definition_ids.append(rubric_id)

        weight, weight_error = safe_weight(definition.get("weight"))
        if weight_error:
            compose_errors.append({"rubric_id": rubric_id, "error": weight_error})
        max_score, max_score_error = safe_max_score(definition.get("max_score"))
        if max_score_error:
            compose_errors.append({"rubric_id": rubric_id, "error": max_score_error})

        source = result_by_id.get(rubric_id)
        if source is None:
            missing_rubrics.append(rubric_id)
            source = {}
            score = 0.0
            passed = False
            message = "missing rubric result"
        else:
            source_max, source_max_error = safe_max_score(source.get("max_score", max_score))
            if source_max_error:
                compose_errors.append({"rubric_id": rubric_id, "error": source_max_error})
            max_score = source_max
            invalid_result = (
                source.get("invalid") is True
                or str(source.get("status") or "").lower() == "invalid"
            )
            source_score = float_or_none(source.get("score"))
            if invalid_result:
                score = 0.0
                passed = False
                message = str(source.get("message") or "invalid rubric result")
                compose_errors.append({"rubric_id": rubric_id, "error": "invalid_rubric_result"})
            elif source_score is None:
                score = 0.0
                passed = False
                message = str(source.get("message") or "invalid rubric score")
                compose_errors.append({"rubric_id": rubric_id, "error": "invalid_score"})
            elif source_score < 0 or source_score > max_score:
                score = 0.0
                passed = False
                message = str(source.get("message") or "rubric score out of range")
                compose_errors.append({"rubric_id": rubric_id, "error": "score_out_of_range"})
            else:
                score = source_score
                threshold = float_or_none(definition.get("pass_threshold"))
                if threshold is None:
                    threshold = 0.5
                passed_value = source.get("passed")
                passed = bool(passed_value) if isinstance(passed_value, bool) else (score / max_score) >= threshold
                message = str(source.get("message") or ("passed" if passed else "failed"))

        normalized = score / max_score if max_score else 0.0
        weighted_score = normalized * weight
        weighted_total += weighted_score
        weight_sum += weight
        raw_score += score
        raw_max_score += max_score

        rubric_payload = dict(source)
        rubric_payload.update({
            "id": rubric_id,
            "name": str(source.get("name") or definition.get("name") or rubric_id),
            "dimension": str(source.get("dimension") or definition.get("dimension") or "quality"),
            "type": canonical_rubric_type(definition, source),
            "passed": passed,
            "score": round_score(score),
            "max_score": round_score(max_score),
            "weight": round_score(weight),
            "weighted_score": round_score(weighted_score),
            "message": message,
        })
        if source.get("test_infra_failure") or source.get("infra_failure"):
            rubric_payload["test_infra_failure"] = True
        if rubric_id in missing_rubrics:
            rubric_payload["missing"] = True
        rubrics.append(rubric_payload)

    extra_rubrics = sorted(rid for rid in result_by_id if rid not in set(definition_ids))
    if extra_rubrics:
        compose_errors.extend({"rubric_id": rid, "error": "extra_rubric_ignored"} for rid in extra_rubrics)

    normalized_score = round_score(weighted_total / weight_sum) if weight_sum > 0 else 0.0
    passed_count = sum(1 for rubric in rubrics if rubric.get("passed"))
    result_metadata = dict(metadata) if metadata else {}
    result_metadata.update({
        "scoring_policy": "case_weighted_v1",
        "raw_score": round_score(raw_score),
        "raw_max_score": round_score(raw_max_score),
        "weighted_raw_score": round_score(weighted_total),
        "weight_sum": round_score(weight_sum),
        "missing_rubrics": missing_rubrics,
        "extra_rubrics": extra_rubrics,
        "compose_errors": compose_errors,
        "input_metadata": [
            payload.get("metadata")
            for payload in input_payloads
            if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict)
        ],
        "input_summaries": [
            str(payload.get("summary"))
            for payload in input_payloads
            if isinstance(payload, dict) and payload.get("summary")
        ],
    })

    payload = {
        "version": "1.0",
        "score": normalized_score,
        "max_score": 1.0,
        "summary": f"weighted score {normalized_score:.4f}, {passed_count}/{len(rubrics)} passed",
        "rubrics": rubrics,
        "agent": agent if isinstance(agent, dict) else {"usage_available": False},
        "metadata": result_metadata,
    }
    validate_result_contract(payload)
    return payload
