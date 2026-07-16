import json
from typing import Any, Dict, List


EVIDENCE_SCHEMA_VERSION = "agent-evidence/v1"


def aggregate_trace_quality(turn_records: List[Dict[str, Any]]) -> str:
    qualities = {str(turn.get("event_trace_quality") or "none") for turn in turn_records}
    if not qualities or qualities == {"none"}:
        return "none"
    if qualities == {"full"}:
        return "full"
    if "partial" in qualities or "full" in qualities:
        return "partial"
    return "raw"


def preview_value(value: Any, *, limit: int = 2000) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated, {len(text)} chars total]"


def compact_json_value(value: Any, *, string_limit: int = 2000, depth: int = 6) -> Any:
    if depth <= 0:
        return preview_value(value, limit=string_limit)
    if isinstance(value, str):
        return preview_value(value, limit=string_limit)
    if isinstance(value, list):
        return [compact_json_value(item, string_limit=string_limit, depth=depth - 1) for item in value[:50]]
    if isinstance(value, dict):
        compacted: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 50:
                compacted["__truncated_keys__"] = len(value) - 50
                break
            compacted[str(key)] = compact_json_value(item, string_limit=string_limit, depth=depth - 1)
        return compacted
    return value


def _event_counts(events: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {"total": len(events)}
    for event in events:
        kind = str(event.get("event_kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _tool_call_evidence(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results_by_id: Dict[str, Dict[str, Any]] = {}
    for event in events:
        if event.get("event_kind") != "tool_result":
            continue
        tool_call_id = str(event.get("tool_call_id") or "")
        if tool_call_id and tool_call_id not in results_by_id:
            results_by_id[tool_call_id] = event

    tool_calls: List[Dict[str, Any]] = []
    for event in events:
        if event.get("event_kind") != "tool_call":
            continue
        tool_call_id = str(event.get("tool_call_id") or "")
        result = results_by_id.get(tool_call_id, {})
        result_value = result.get("tool_output")
        if result_value is None:
            result_value = result.get("text")
        tool_input = compact_json_value(event.get("tool_input"))
        tool_calls.append(
            {
                "tool_call_id": tool_call_id or None,
                "tool_name": event.get("tool_name"),
                "tool_input": tool_input,
                "tool_input_preview": preview_value(tool_input),
                "tool_result_preview": preview_value(result_value),
                "is_error": bool(result.get("is_error")),
            }
        )
    return tool_calls


def build_agent_evidence(
    *,
    agent_type: str,
    model: str,
    mode: str,
    session_id: str,
    source_turns: List[Dict[str, Any]],
    trace_turns: List[Dict[str, Any]],
    all_events: List[Dict[str, Any]],
    agent_usage: Dict[str, Any],
) -> Dict[str, Any]:
    events_by_turn: Dict[str, List[Dict[str, Any]]] = {}
    for event in all_events:
        turn_id = str(event.get("turn_id") or "")
        events_by_turn.setdefault(turn_id, []).append(event)

    evidence_turns = []
    for index, trace_turn in enumerate(trace_turns):
        turn_id = str(trace_turn.get("turn_id") or f"turn-{index + 1}")
        source_turn = source_turns[index] if index < len(source_turns) else {}
        turn_events = events_by_turn.get(turn_id, [])
        evidence_turns.append(
            {
                "turn_id": turn_id,
                "turn_index": trace_turn.get("turn_index"),
                "agent_type": trace_turn.get("agent_type") or agent_type,
                "model": trace_turn.get("model") or model,
                "session_id": trace_turn.get("session_id"),
                "returncode": trace_turn.get("returncode"),
                "started_at": trace_turn.get("started_at"),
                "ended_at": trace_turn.get("ended_at"),
                "duration_ms": trace_turn.get("duration_ms"),
                "input": {
                    "path": (trace_turn.get("input") or {}).get("path"),
                    "text": str(source_turn.get("user") or ""),
                    "context": source_turn.get("context"),
                },
                "effective_input": {
                    "path": (trace_turn.get("effective_input") or {}).get("path"),
                    "text": (trace_turn.get("effective_input") or {}).get("text") or "",
                },
                "system_instruction_included": trace_turn.get("system_instruction_included"),
                "visible_output": {
                    "path": (trace_turn.get("visible_output") or {}).get("path"),
                    "text": (trace_turn.get("visible_output") or {}).get("text") or "",
                },
                "event_trace_quality": trace_turn.get("event_trace_quality"),
                "event_counts": _event_counts(turn_events),
                "tool_calls": _tool_call_evidence(turn_events),
                "usage": trace_turn.get("usage") or {},
            }
        )

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "agent_type": agent_type,
        "model": model,
        "mode": mode,
        "session_id": session_id,
        "artifacts": {
            "agent_trace": "agent_trace.json",
            "agent_events": "agent_events.jsonl",
            "agent_output": "agent_output.txt",
            "agent_usage": "agent_usage.json",
        },
        "usage": agent_usage,
        "event_trace_quality": aggregate_trace_quality(trace_turns),
        "turns": evidence_turns,
    }
