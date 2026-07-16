import json
from pathlib import Path
from typing import Any, Dict, List, Union

from payskills_runtime.agent.evidence import aggregate_trace_quality, build_agent_evidence


TRACE_SCHEMA_VERSION = "agent-trace/v1"


def read_optional_text(path: Union[str, Path]) -> str:
    try:
        file_path = Path(path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", errors="replace") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def relative_to_output(path: Path, output_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(path)


def write_agent_run_artifacts(
    output_dir: Path,
    *,
    agent_type: str,
    model: str,
    mode: str,
    session_id: str,
    instruction_path: Path,
    system_instruction_text: str,
    source_turns: List[Dict[str, Any]],
    trace_turns: List[Dict[str, Any]],
    all_events: List[Dict[str, Any]],
    agent_usage: Dict[str, Any],
    combined_input: List[str],
    combined_output: List[str],
    run_records: List[Dict[str, Any]],
    status: str = "completed",
) -> None:
    write_text(output_dir / "agent_input.txt", "\n\n".join(combined_input).rstrip() + "\n")
    write_text(output_dir / "agent_output.txt", "\n\n".join(combined_output).rstrip() + "\n")
    write_text(output_dir / "agent_usage.json", json.dumps(agent_usage, ensure_ascii=False, indent=2) + "\n")
    write_jsonl(output_dir / "agent_events.jsonl", all_events)

    agent_evidence = build_agent_evidence(
        agent_type=agent_type,
        model=model,
        mode=mode,
        session_id=session_id,
        source_turns=source_turns,
        trace_turns=trace_turns,
        all_events=all_events,
        agent_usage=agent_usage,
    )
    write_text(output_dir / "agent_evidence.json", json.dumps(agent_evidence, ensure_ascii=False, indent=2) + "\n")
    write_text(
        output_dir / "agent_trace.json",
        json.dumps(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "agent_type": agent_type,
                "model": model,
                "mode": mode,
                "session_id": session_id,
                "system_instruction": {
                    "path": str(instruction_path),
                    "text": system_instruction_text,
                },
                "usage": agent_usage,
                "event_trace_quality": aggregate_trace_quality(trace_turns),
                "turns": trace_turns,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        output_dir / "agent_run.json",
        json.dumps(
            {
                "agent_type": agent_type,
                "model": model,
                "session_id": session_id,
                "status": status,
                "usage": agent_usage,
                "turns": run_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    write_text(output_dir / "agent_status.txt", status + "\n")
