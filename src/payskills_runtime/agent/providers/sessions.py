import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from payskills_runtime.agent.events import parse_raw_events


def extract_openclaw_metadata(stdout: str) -> Dict[str, str]:
    raw_events, _ = parse_raw_events(stdout)
    for event in reversed(raw_events):
        if not isinstance(event, dict):
            continue
        meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        session_id = agent_meta.get("sessionId") or event.get("sessionId") or event.get("session_id")
        session_file = agent_meta.get("sessionFile") or event.get("sessionFile")
        if session_id or session_file:
            return {
                "session_id": str(session_id or ""),
                "session_file": str(session_file or ""),
            }
    return {"session_id": "", "session_file": ""}


def extract_session_id_from_output(agent_type: str, stdout: str, stderr: str, fallback: str) -> str:
    if agent_type == "claude-code":
        raw_events, _ = parse_raw_events(stdout)
        for event in reversed(raw_events):
            session_id = event.get("session_id") if isinstance(event, dict) else None
            if session_id:
                return str(session_id)
    if agent_type == "openclaw":
        metadata = extract_openclaw_metadata(stdout)
        if metadata.get("session_id"):
            return metadata["session_id"]
    if agent_type == "hermes":
        for text in (stderr, stdout):
            match = re.search(r"session_id:\s*([^\s]+)", text)
            if match:
                return match.group(1)
    return fallback


def openclaw_session_path(home: Path, session_id: str) -> Path:
    return home / ".openclaw" / "agents" / "coder" / "sessions" / f"{session_id}.jsonl"


def sqlite_max_id(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(str(path)) as conn:
            row = conn.execute(f"SELECT max(id) FROM {table}").fetchone()
    except sqlite3.Error:
        return 0
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def read_hermes_messages(path: Path, *, since_id: int, session_id: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        columns = [row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "id" not in columns:
            conn.close()
            return []
        column_sql = ", ".join(f'"{column}"' for column in columns)
        params: List[Any] = [since_id]
        where = "id > ?"
        if session_id and "session_id" in columns:
            where += " AND session_id = ?"
            params.append(session_id)
        rows = conn.execute(f"SELECT {column_sql} FROM messages WHERE {where} ORDER BY id ASC", params).fetchall()
        if not rows and session_id and "session_id" in columns:
            rows = conn.execute(f"SELECT {column_sql} FROM messages WHERE id > ? ORDER BY id ASC", [since_id]).fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    records: List[Dict[str, Any]] = []
    for row in rows:
        record = {key: row[key] for key in row.keys()}
        record["type"] = "hermes_message"
        record["_source"] = "hermes_state_db"
        record["_source_event_index"] = len(records) + 1
        records.append(record)
    return records
