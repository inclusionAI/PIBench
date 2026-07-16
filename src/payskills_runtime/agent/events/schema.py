from typing import Any, Dict, List

from payskills_runtime.agent.usage import event_usage_from_raw, usage_for_event


EVENT_SCHEMA_VERSION = "agent-event/v1"
EVENT_FIELDS = (
    "schema_version",
    "event_id",
    "event_index",
    "turn_id",
    "session_id",
    "agent_type",
    "event_kind",
    "source",
    "source_event_index",
    "timestamp",
    "role",
    "text",
    "tool_call_id",
    "tool_name",
    "tool_input",
    "tool_output",
    "is_error",
    "usage",
    "subtype",
    "raw_event_type",
    "raw_event",
)
PROVIDER_TRACE_SOURCES = {"claude_stream_json", "openclaw_session_jsonl", "hermes_state_db"}


def complete_event(event: Dict[str, Any]) -> Dict[str, Any]:
    completed = {field: None for field in EVENT_FIELDS}
    completed["schema_version"] = EVENT_SCHEMA_VERSION
    completed["event_id"] = ""
    completed["event_index"] = 0
    completed["raw_event"] = {}
    completed.update(event)
    return completed


def finalize_events(events: List[Dict[str, Any]], turn_id: str) -> List[Dict[str, Any]]:
    finalized = []
    for index, event in enumerate(events, start=1):
        item = dict(event)
        item["event_index"] = index
        item["event_id"] = f"{turn_id}:{index:06d}"
        finalized.append(complete_event(item))
    return finalized


def _normalized_event_base(
    *,
    agent_type: str,
    turn_id: str,
    session_id: str,
    event_kind: str,
    raw_event: Dict[str, Any],
) -> Dict[str, Any]:
    message = raw_event.get("message") if isinstance(raw_event.get("message"), dict) else {}
    role = raw_event.get("role") or message.get("role")
    source = raw_event.get("_source")
    if not source:
        source = "claude_stream_json" if agent_type == "claude-code" else "stdout_json"
    event = complete_event(
        {
            "schema_version": EVENT_SCHEMA_VERSION,
            "agent_type": agent_type,
            "turn_id": turn_id,
            "session_id": session_id,
            "event_kind": event_kind,
            "source": str(source),
            "source_event_index": raw_event.get("_source_event_index") or raw_event.get("_raw_line"),
            "timestamp": raw_event.get("timestamp"),
            "role": str(role) if role is not None else None,
            "raw_event_type": raw_event.get("type"),
            "raw_event": raw_event,
        }
    )
    event_usage = event_usage_from_raw(agent_type, raw_event)
    usage_payload = usage_for_event(event_usage) if event_usage else None
    if usage_payload:
        event["usage"] = usage_payload
    return event


def trace_quality(agent_type: str, parse_kind: str, events: List[Dict[str, Any]]) -> str:
    if not events:
        return "none"
    has_final = any(event.get("event_kind") == "final_result" for event in events)
    has_provider_trace = any(event.get("source") in PROVIDER_TRACE_SOURCES for event in events)
    has_internal_event = any(
        event.get("event_kind")
        in {"session", "thinking", "tool_call", "tool_result", "assistant_text", "user_message", "user_text"}
        for event in events
    )
    if has_final and has_provider_trace and has_internal_event:
        return "full"
    if has_final:
        return "partial"
    if parse_kind in {"json", "jsonl", "mixed", "text"}:
        return "raw"
    return "none"
