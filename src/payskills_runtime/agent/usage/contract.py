from typing import Any, Dict, List, Optional


USAGE_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_tokens",
)
USAGE_NUMBER_FIELDS = USAGE_TOKEN_FIELDS + (
    "total_cost_usd",
    "duration_ms",
    "duration_api_ms",
    "api_call_count",
)


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0) if value == value else 0
    if isinstance(value, str):
        try:
            return max(int(float(value)), 0)
        except ValueError:
            return 0
    return 0


def _float_or_zero(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str):
        try:
            return max(float(value), 0.0)
        except ValueError:
            return 0.0
    return 0.0


def base_usage(agent_type: str, model: str, source: str, *, available: bool) -> Dict[str, Any]:
    return {
        "usage_available": bool(available),
        "agent_type": agent_type,
        "model": model,
        "source": source,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_cost_usd": 0.0,
        "duration_ms": 0,
        "duration_api_ms": 0,
        "api_call_count": 0,
    }


def unavailable_usage(agent_type: str, model: str, source: str = "unavailable") -> Dict[str, Any]:
    return base_usage(agent_type, model, source, available=False)


def usage_delta(after: Dict[str, Any], before: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    if not after.get("usage_available"):
        return dict(after)
    delta = base_usage(str(after.get("agent_type") or ""), str(after.get("model") or ""), source, available=True)
    for field in USAGE_NUMBER_FIELDS:
        value = _float_or_zero(after.get(field)) - (_float_or_zero(before.get(field)) if before.get("usage_available") else 0.0)
        if field in {"total_cost_usd"}:
            delta[field] = max(value, 0.0)
        else:
            delta[field] = max(int(value), 0)
    return delta


def usage_for_event(usage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(usage, dict) or not usage.get("usage_available"):
        return None
    return {
        "source": usage.get("source"),
        "input_tokens": _int_or_zero(usage.get("input_tokens")),
        "output_tokens": _int_or_zero(usage.get("output_tokens")),
        "cache_read_input_tokens": _int_or_zero(usage.get("cache_read_input_tokens")),
        "cache_creation_input_tokens": _int_or_zero(usage.get("cache_creation_input_tokens")),
        "reasoning_tokens": _int_or_zero(usage.get("reasoning_tokens")),
        "total_cost_usd": _float_or_zero(usage.get("total_cost_usd")),
        "duration_ms": _int_or_zero(usage.get("duration_ms")),
        "duration_api_ms": _int_or_zero(usage.get("duration_api_ms")),
        "api_call_count": _int_or_zero(usage.get("api_call_count")),
    }


def attach_turn_usage_to_final_event(events: List[Dict[str, Any]], turn_usage: Dict[str, Any]) -> List[Dict[str, Any]]:
    event_usage = usage_for_event(turn_usage)
    if not event_usage or not events:
        return events
    target_index = None
    for index, event in enumerate(events):
        if event.get("event_kind") == "final_result":
            target_index = index
    if target_index is None:
        target_index = len(events) - 1
    updated = [dict(event) for event in events]
    if not updated[target_index].get("usage"):
        updated[target_index]["usage"] = event_usage
    return updated


def aggregate_agent_usage(
    *,
    agent_type: str,
    model: str,
    mode: str,
    session_id: str,
    turn_usages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    available_turns = [usage for usage in turn_usages if usage.get("usage_available")]
    if not available_turns:
        usage = unavailable_usage(agent_type, model)
        usage["mode"] = mode
        usage["session_id"] = session_id
        usage["num_turns"] = 0
        usage["turns"] = turn_usages
        return usage
    sources = sorted({str(usage.get("source") or "") for usage in available_turns if usage.get("source")})
    aggregate = base_usage(agent_type, model, sources[0] if len(sources) == 1 else "mixed", available=True)
    aggregate["mode"] = mode
    aggregate["session_id"] = session_id
    aggregate["num_turns"] = len(available_turns)
    aggregate["turns"] = turn_usages
    if len(sources) > 1:
        aggregate["sources"] = sources
    for usage in available_turns:
        for field in USAGE_NUMBER_FIELDS:
            if field == "total_cost_usd":
                aggregate[field] = _float_or_zero(aggregate.get(field)) + _float_or_zero(usage.get(field))
            else:
                aggregate[field] = _int_or_zero(aggregate.get(field)) + _int_or_zero(usage.get(field))
    return aggregate
