import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from payskills_runtime.agent.artifacts import write_jsonl
from payskills_runtime.agent.events import normalize_hermes_provider_events, normalize_openclaw_provider_events, wrap_raw_event
from payskills_runtime.agent.providers import (
    extract_openclaw_metadata,
    openclaw_session_path,
    read_hermes_messages,
    sqlite_max_id,
)


def jsonl_line_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for count, _ in enumerate(f, start=1):
            pass
    return count


def read_jsonl_records(path: Path, *, start_line: int = 0, source: str = "") -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            if line_no <= start_line:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except Exception:
                record = {"type": "raw_text", "line": line_no, "text": line.rstrip("\n")}
            else:
                record = wrap_raw_event(payload)
                record.setdefault("_raw_line", line_no)
            if source:
                record["_source"] = source
            record["_source_event_index"] = len(records) + 1
            records.append(record)
    return records


def build_provider_trace_context(agent_type: str, home: Path, session_id: str, resume_session_id: str) -> Dict[str, Any]:
    openclaw_session_arg = resume_session_id or session_id
    openclaw_session_file = openclaw_session_path(home, openclaw_session_arg)
    hermes_db_path = home / ".hermes" / "state.db"
    return {
        "openclaw_session_arg": openclaw_session_arg,
        "openclaw_session_file": openclaw_session_file,
        "openclaw_start_line": jsonl_line_count(openclaw_session_file) if agent_type == "openclaw" else 0,
        "hermes_db_path": hermes_db_path,
        "hermes_before_id": sqlite_max_id(hermes_db_path, "messages") if agent_type == "hermes" else 0,
    }


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _empty_capture() -> Dict[str, Any]:
    return {
        "provider_records": [],
        "provider_events": [],
        "provider_trace_source": "",
        "provider_trace_path": None,
    }


def capture_provider_trace(
    agent_type: str,
    *,
    raw: str,
    raw_events: List[Dict[str, Any]],
    home: Path,
    turn_dir: Path,
    raw_events_path: Path,
    turn_id: str,
    turn_session_id: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    if agent_type == "claude-code":
        return {
            "provider_records": raw_events,
            "provider_events": [],
            "provider_trace_source": "claude_stream_json",
            "provider_trace_path": raw_events_path,
        }

    if agent_type == "openclaw":
        metadata = extract_openclaw_metadata(raw)
        session_file_text = metadata.get("session_file") or ""
        session_file = Path(session_file_text) if session_file_text else openclaw_session_path(home, turn_session_id)
        same_file = _same_path(session_file, Path(context["openclaw_session_file"]))
        provider_records = read_jsonl_records(
            session_file,
            start_line=int(context.get("openclaw_start_line") or 0) if same_file else 0,
            source="openclaw_session_jsonl",
        )
        if not provider_records:
            return _empty_capture()
        provider_trace_path = turn_dir / "provider_trace" / "openclaw_session.jsonl"
        write_jsonl(provider_trace_path, provider_records)
        return {
            "provider_records": provider_records,
            "provider_events": normalize_openclaw_provider_events(provider_records, turn_id, turn_session_id),
            "provider_trace_source": "openclaw_session_jsonl",
            "provider_trace_path": provider_trace_path,
        }

    if agent_type == "hermes":
        provider_records = read_hermes_messages(
            Path(context["hermes_db_path"]),
            since_id=int(context.get("hermes_before_id") or 0),
            session_id=turn_session_id,
        )
        if not provider_records:
            return _empty_capture()
        provider_trace_path = turn_dir / "provider_trace" / "hermes_messages.jsonl"
        write_jsonl(provider_trace_path, provider_records)
        return {
            "provider_records": provider_records,
            "provider_events": normalize_hermes_provider_events(provider_records, turn_id, turn_session_id),
            "provider_trace_source": "hermes_state_db",
            "provider_trace_path": provider_trace_path,
        }

    return _empty_capture()
