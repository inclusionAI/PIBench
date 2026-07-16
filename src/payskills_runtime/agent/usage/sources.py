import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from payskills_runtime.agent.usage.contract import (
    USAGE_NUMBER_FIELDS,
    _float_or_zero,
    _int_or_zero,
    base_usage,
    unavailable_usage,
)


def canonical_claude_usage(raw_usage: Any, raw_event: Dict[str, Any], *, model: str, source: str) -> Dict[str, Any]:
    if not isinstance(raw_usage, dict):
        return unavailable_usage("claude-code", model, source)
    usage = base_usage("claude-code", model, source, available=True)
    usage["input_tokens"] = _int_or_zero(raw_usage.get("input_tokens"))
    usage["output_tokens"] = _int_or_zero(raw_usage.get("output_tokens"))
    usage["cache_read_input_tokens"] = _int_or_zero(raw_usage.get("cache_read_input_tokens"))
    usage["cache_creation_input_tokens"] = _int_or_zero(raw_usage.get("cache_creation_input_tokens"))
    usage["reasoning_tokens"] = _int_or_zero(raw_usage.get("reasoning_tokens"))
    usage["duration_ms"] = _int_or_zero(raw_event.get("duration_ms"))
    usage["duration_api_ms"] = _int_or_zero(raw_event.get("duration_api_ms"))
    usage["total_cost_usd"] = _float_or_zero(raw_event.get("total_cost_usd"))
    usage["api_call_count"] = 1
    return usage


def canonical_openclaw_usage(raw_usage: Any, *, model: str, source: str) -> Dict[str, Any]:
    if not isinstance(raw_usage, dict):
        return unavailable_usage("openclaw", model, source)
    usage = base_usage("openclaw", model, source, available=True)
    usage["input_tokens"] = _int_or_zero(raw_usage.get("input") or raw_usage.get("inputTokens") or raw_usage.get("input_tokens"))
    usage["output_tokens"] = _int_or_zero(raw_usage.get("output") or raw_usage.get("outputTokens") or raw_usage.get("output_tokens"))
    usage["cache_read_input_tokens"] = _int_or_zero(
        raw_usage.get("cacheRead") or raw_usage.get("cacheReadTokens") or raw_usage.get("cache_read_input_tokens")
    )
    usage["cache_creation_input_tokens"] = _int_or_zero(
        raw_usage.get("cacheWrite") or raw_usage.get("cacheWriteTokens") or raw_usage.get("cache_creation_input_tokens")
    )
    cost = raw_usage.get("cost") if isinstance(raw_usage.get("cost"), dict) else {}
    usage["total_cost_usd"] = _float_or_zero(cost.get("total") or raw_usage.get("total_cost_usd"))
    usage["api_call_count"] = 1
    return usage


def read_hermes_session_usage(path: Path, session_id: str, *, model: str) -> Dict[str, Any]:
    if not path.exists() or not session_id:
        return unavailable_usage("hermes", model, "hermes_state_db_sessions")
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        columns = [row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "id" not in columns:
            conn.close()
            return unavailable_usage("hermes", model, "hermes_state_db_sessions")
        wanted = [
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "estimated_cost_usd",
            "actual_cost_usd",
            "api_call_count",
        ]
        select_columns = ["id"] + [column for column in wanted if column in columns]
        column_sql = ", ".join(f'"{column}"' for column in select_columns)
        row = conn.execute(f"SELECT {column_sql} FROM sessions WHERE id = ?", [session_id]).fetchone()
        conn.close()
    except sqlite3.Error:
        return unavailable_usage("hermes", model, "hermes_state_db_sessions")
    if row is None:
        return unavailable_usage("hermes", model, "hermes_state_db_sessions")

    usage = base_usage("hermes", model, "hermes_state_db_sessions", available=True)
    usage["input_tokens"] = _int_or_zero(row["input_tokens"] if "input_tokens" in row.keys() else 0)
    usage["output_tokens"] = _int_or_zero(row["output_tokens"] if "output_tokens" in row.keys() else 0)
    usage["cache_read_input_tokens"] = _int_or_zero(row["cache_read_tokens"] if "cache_read_tokens" in row.keys() else 0)
    usage["cache_creation_input_tokens"] = _int_or_zero(row["cache_write_tokens"] if "cache_write_tokens" in row.keys() else 0)
    usage["reasoning_tokens"] = _int_or_zero(row["reasoning_tokens"] if "reasoning_tokens" in row.keys() else 0)
    actual_cost = row["actual_cost_usd"] if "actual_cost_usd" in row.keys() else None
    estimated_cost = row["estimated_cost_usd"] if "estimated_cost_usd" in row.keys() else None
    usage["total_cost_usd"] = _float_or_zero(actual_cost if actual_cost is not None else estimated_cost)
    usage["api_call_count"] = _int_or_zero(row["api_call_count"] if "api_call_count" in row.keys() else 0)
    return usage


def extract_claude_turn_usage(raw_events: List[Dict[str, Any]], *, model: str) -> Dict[str, Any]:
    for event in reversed(raw_events):
        if isinstance(event, dict) and event.get("type") == "result" and isinstance(event.get("usage"), dict):
            return canonical_claude_usage(event.get("usage"), event, model=model, source="claude_result_usage")
    for event in reversed(raw_events):
        message = event.get("message") if isinstance(event, dict) and isinstance(event.get("message"), dict) else {}
        if isinstance(message.get("usage"), dict):
            return canonical_claude_usage(message.get("usage"), event, model=model, source="claude_message_usage")
    return unavailable_usage("claude-code", model)


def extract_openclaw_turn_usage(
    raw_events: List[Dict[str, Any]],
    provider_records: List[Dict[str, Any]],
    *,
    model: str,
) -> Dict[str, Any]:
    for event in reversed(raw_events):
        meta = event.get("meta") if isinstance(event, dict) and isinstance(event.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        raw_usage = agent_meta.get("usage")
        if isinstance(raw_usage, dict):
            return canonical_openclaw_usage(raw_usage, model=model, source="openclaw_stdout_usage")
    totals = base_usage("openclaw", model, "openclaw_session_jsonl_usage", available=False)
    found = False
    for record in provider_records:
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        raw_usage = message.get("usage")
        if not isinstance(raw_usage, dict):
            continue
        item = canonical_openclaw_usage(raw_usage, model=model, source="openclaw_session_jsonl_usage")
        for field in USAGE_NUMBER_FIELDS:
            if field == "total_cost_usd":
                totals[field] = _float_or_zero(totals.get(field)) + _float_or_zero(item.get(field))
            else:
                totals[field] = _int_or_zero(totals.get(field)) + _int_or_zero(item.get(field))
        found = True
    if found:
        totals["usage_available"] = True
    return totals if found else unavailable_usage("openclaw", model)


def event_usage_from_raw(agent_type: str, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if agent_type == "claude-code":
        model = str(raw_event.get("model") or "")
        if isinstance(raw_event.get("usage"), dict):
            return canonical_claude_usage(raw_event.get("usage"), raw_event, model=model, source="claude_result_usage")
        message = raw_event.get("message") if isinstance(raw_event.get("message"), dict) else {}
        if isinstance(message.get("usage"), dict):
            return canonical_claude_usage(message.get("usage"), raw_event, model=model, source="claude_message_usage")
    if agent_type == "openclaw":
        message = raw_event.get("message") if isinstance(raw_event.get("message"), dict) else {}
        if isinstance(message.get("usage"), dict):
            return canonical_openclaw_usage(message.get("usage"), model="", source="openclaw_session_jsonl_usage")
        meta = raw_event.get("meta") if isinstance(raw_event.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        if isinstance(agent_meta.get("usage"), dict):
            return canonical_openclaw_usage(agent_meta.get("usage"), model="", source="openclaw_stdout_usage")
    return None
