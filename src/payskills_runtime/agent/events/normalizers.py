from typing import Any, Dict, List

from payskills_runtime.agent.events.claude import normalize_claude_event
from payskills_runtime.agent.events.hermes import normalize_hermes_provider_events
from payskills_runtime.agent.events.openclaw import normalize_openclaw_provider_events
from payskills_runtime.agent.events.schema import finalize_events
from payskills_runtime.agent.events.stdout import normalize_stdout_event, visible_final_result_event


def normalize_agent_events(
    *,
    agent_type: str,
    raw_events: List[Dict[str, Any]],
    turn_id: str,
    session_id: str,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw_event in raw_events:
        if agent_type == "claude-code":
            normalized.extend(normalize_claude_event(raw_event, turn_id, session_id))
        else:
            normalized.extend(
                normalize_stdout_event(
                    raw_event,
                    agent_type=agent_type,
                    turn_id=turn_id,
                    session_id=session_id,
                )
            )

    return finalize_events(normalized, turn_id)
