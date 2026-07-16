import argparse
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from payskills_runtime.agent.artifacts import read_optional_text, write_agent_run_artifacts, write_jsonl, write_text
from payskills_runtime.agent.events import (
    finalize_events,
    normalize_agent_events,
    parse_raw_events,
    trace_quality,
    visible_final_result_event,
)
from payskills_runtime.agent.invocation import (
    agent_command_timeout,
    build_agent_environment,
    build_agent_turn_command,
    prepare_agent_turn,
    run_command,
)
from payskills_runtime.agent.prompts import build_effective_turn_prompt, build_turn_message, load_turns
from payskills_runtime.agent.providers import extract_session_id_from_output
from payskills_runtime.agent.providers.traces import build_provider_trace_context, capture_provider_trace
from payskills_runtime.agent.skills import prepare_skills
from payskills_runtime.agent.turn_records import build_agent_run_record, build_agent_trace_turn
from payskills_runtime.agent.usage import (
    aggregate_agent_usage,
    attach_turn_usage_to_final_event,
    extract_claude_turn_usage,
    extract_openclaw_turn_usage,
    read_hermes_session_usage,
    unavailable_usage,
    usage_delta,
)
from payskills_runtime.agent.visible_output import extract_visible_output


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def drive_turns(args: argparse.Namespace) -> int:
    agent_type = args.agent_type
    workspace = Path(args.workspace).resolve()
    output_dir = Path(args.output_dir).resolve()
    skills_dir = Path(args.skills).resolve()
    home = Path(args.home or os.environ.get("HOME", "/home/agent")).resolve()
    timeout = int(args.timeout or os.environ.get("AGENT_TIMEOUT", "600"))
    model = args.model or os.environ.get("AGENT_MODEL", "")
    mode = args.mode or os.environ.get("AGENT_MODE", "default")

    base_env = build_agent_environment(agent_type, home, workspace, model)
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    prepare_skills(
        agent_type,
        mode,
        skills_dir,
        workspace,
        home,
        openclaw_profile=args.openclaw_profile,
        claude_config_dir=base_env.get("CLAUDE_CONFIG_DIR"),
    )

    turns = load_turns(args.turns)
    instruction_path = Path(args.instruction)
    system_instruction_text = read_optional_text(instruction_path)
    combined_input = []
    combined_output = []
    session_id = args.session_id or str(uuid.uuid4())
    resume_session_id = session_id if agent_type in {"claude-code", "openclaw"} else ""
    run_records = []
    trace_turns = []
    turn_usages: List[Dict[str, Any]] = []
    all_events: List[Dict[str, Any]] = []

    for index, turn in enumerate(turns, start=1):
        turn_id = str(turn.get("id") or f"turn-{index}")
        turn_dir = output_dir / "turns" / turn_id
        turn_message = build_turn_message(
            turn,
            skill_trigger=args.skill_trigger,
            skill_name=args.skill_name,
        )
        include_system_instruction = index == 1 and bool(system_instruction_text.strip())
        effective_input = build_effective_turn_prompt(
            turn_message,
            system_instruction_text,
            include_system_instruction=include_system_instruction,
        )
        write_text(turn_dir / "input.txt", turn_message)
        write_text(turn_dir / "effective_input.txt", effective_input)
        combined_input.append(f"=== {turn_id} ===\n{effective_input}")

        stdout_path = turn_dir / "raw_stdout.txt"
        stderr_path = turn_dir / "raw_stderr.txt"
        raw_events_path = turn_dir / "raw_events.jsonl"
        events_path = turn_dir / "events.jsonl"
        provider_context = build_provider_trace_context(agent_type, home, session_id, resume_session_id)
        openclaw_session_arg = str(provider_context["openclaw_session_arg"])
        hermes_db_path = Path(provider_context["hermes_db_path"])
        hermes_before_usage = (
            read_hermes_session_usage(hermes_db_path, resume_session_id or session_id, model=model)
            if agent_type == "hermes"
            else unavailable_usage(agent_type, model)
        )
        started_at = _utc_now()
        started_perf = time.perf_counter()
        prepare_agent_turn(agent_type, turn_index=index, workspace=workspace, env=base_env)
        cmd = build_agent_turn_command(
            agent_type,
            model=model,
            max_turns=args.max_turns,
            session_id=session_id,
            resume_session_id=resume_session_id,
            turn_index=index,
            turn_message=turn_message,
            effective_input=effective_input,
            include_system_instruction=include_system_instruction,
            system_instruction=system_instruction_text,
            openclaw_session_arg=openclaw_session_arg,
            timeout=timeout,
        )
        rc = run_command(
            cmd,
            cwd=workspace,
            env=base_env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=agent_command_timeout(agent_type, timeout),
        )
        ended_at = _utc_now()
        duration_ms = int((time.perf_counter() - started_perf) * 1000)

        raw = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        raw_stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        turn_session_id = extract_session_id_from_output(agent_type, raw, raw_stderr, session_id)
        if turn_session_id:
            session_id = turn_session_id
            resume_session_id = turn_session_id
        visible = extract_visible_output(raw, agent_type)
        write_text(turn_dir / "output.txt", visible)
        combined_output.append(f"=== {turn_id} ===\n{visible}")
        raw_events, raw_parse_kind = parse_raw_events(raw)
        stdout_events = normalize_agent_events(
            agent_type=agent_type,
            raw_events=raw_events,
            turn_id=turn_id,
            session_id=turn_session_id,
        )

        provider_capture = capture_provider_trace(
            agent_type,
            raw=raw,
            raw_events=raw_events,
            home=home,
            turn_dir=turn_dir,
            raw_events_path=raw_events_path,
            turn_id=turn_id,
            turn_session_id=turn_session_id,
            context=provider_context,
        )
        provider_records = provider_capture["provider_records"]
        provider_events = provider_capture["provider_events"]
        provider_trace_source = provider_capture["provider_trace_source"]
        provider_trace_path = provider_capture["provider_trace_path"]

        if provider_events and visible.strip() and not any(event.get("event_kind") == "final_result" for event in stdout_events):
            stdout_events = [visible_final_result_event(agent_type, turn_id, turn_session_id, visible)]
        normalized_events = finalize_events(provider_events + stdout_events, turn_id) if provider_events else stdout_events

        if agent_type == "claude-code":
            turn_usage = extract_claude_turn_usage(raw_events, model=model)
        elif agent_type == "openclaw":
            turn_usage = extract_openclaw_turn_usage(raw_events, provider_records, model=model)
        elif agent_type == "hermes":
            hermes_after_usage = read_hermes_session_usage(hermes_db_path, turn_session_id, model=model)
            turn_usage = usage_delta(hermes_after_usage, hermes_before_usage, source="hermes_state_db_sessions")
        else:
            turn_usage = unavailable_usage(agent_type, model)
        turn_usage["turn_id"] = turn_id
        turn_usage["session_id"] = turn_session_id
        if not turn_usage.get("duration_ms"):
            turn_usage["duration_ms"] = duration_ms
        turn_usages.append(turn_usage)
        normalized_events = attach_turn_usage_to_final_event(normalized_events, turn_usage)

        event_trace_quality = trace_quality(agent_type, raw_parse_kind, normalized_events)
        write_jsonl(raw_events_path, raw_events)
        write_jsonl(events_path, normalized_events)
        all_events.extend(normalized_events)

        run_records.append(
            build_agent_run_record(
                turn_id=turn_id,
                returncode=rc,
                turn_dir=turn_dir,
                raw_events_path=raw_events_path,
                events_path=events_path,
                event_trace_quality=event_trace_quality,
                usage=turn_usage,
            )
        )
        trace_turns.append(
            build_agent_trace_turn(
                turn_id=turn_id,
                turn_index=index,
                agent_type=agent_type,
                model=model,
                session_id=turn_session_id,
                returncode=rc,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                turn_dir=turn_dir,
                output_dir=output_dir,
                turn_message=turn_message,
                effective_input=effective_input,
                include_system_instruction=include_system_instruction,
                raw_stdout_path=stdout_path,
                raw_stderr_path=stderr_path,
                raw_stdout_text=raw,
                raw_stderr_text=raw_stderr,
                raw_events_path=raw_events_path,
                events_path=events_path,
                provider_trace_path=provider_trace_path,
                provider_trace_source=provider_trace_source,
                provider_event_count=len(provider_records),
                visible=visible,
                event_count=len(normalized_events),
                raw_event_count=len(raw_events),
                raw_event_parse_kind=raw_parse_kind,
                event_trace_quality=event_trace_quality,
                usage=turn_usage,
            )
        )

    agent_usage = aggregate_agent_usage(
        agent_type=agent_type,
        model=model,
        mode=mode,
        session_id=session_id,
        turn_usages=turn_usages,
    )
    agent_exit = 0
    for record in run_records:
        try:
            returncode = int(record.get("returncode") or 0)
        except Exception:
            returncode = 1
        if returncode != 0:
            agent_exit = returncode
            break
    agent_status = "completed" if agent_exit == 0 else "failed"
    write_agent_run_artifacts(
        output_dir,
        agent_type=agent_type,
        model=model,
        mode=mode,
        session_id=session_id,
        instruction_path=instruction_path,
        system_instruction_text=system_instruction_text,
        source_turns=turns,
        trace_turns=trace_turns,
        all_events=all_events,
        agent_usage=agent_usage,
        combined_input=combined_input,
        combined_output=combined_output,
        run_records=run_records,
        status=agent_status,
    )
    return agent_exit
