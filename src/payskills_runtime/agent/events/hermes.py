from typing import Any, Dict, List

from payskills_runtime.agent.events.parsing import _content_text, _json_loads_maybe, _tool_call_name_and_input
from payskills_runtime.agent.events.schema import _normalized_event_base


def normalize_hermes_provider_events(records: List[Dict[str, Any]], turn_id: str, session_id: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if records:
        first = records[0]
        session_event = _normalized_event_base(
            agent_type="hermes",
            turn_id=turn_id,
            session_id=str(first.get("session_id") or session_id),
            event_kind="session",
            raw_event={
                "type": "session",
                "session_id": str(first.get("session_id") or session_id),
                "timestamp": first.get("timestamp"),
                "_source": "hermes_state_db",
                "_source_event_index": -1,
                "synthetic": True,
            },
        )
        normalized.append(session_event)
    for raw_event in records:
        role = str(raw_event.get("role") or "")
        event_session_id = str(raw_event.get("session_id") or session_id)
        content = raw_event.get("content")
        if role == "user":
            text = _content_text(content)
            if text:
                event = _normalized_event_base(
                    agent_type="hermes",
                    turn_id=turn_id,
                    session_id=event_session_id,
                    event_kind="user_message",
                    raw_event=raw_event,
                )
                event["text"] = text
                normalized.append(event)
            continue

        if role == "assistant":
            reasoning_text = _content_text(raw_event.get("reasoning_content") or raw_event.get("reasoning") or "")
            if not reasoning_text and raw_event.get("reasoning_details"):
                reasoning_text = _content_text(_json_loads_maybe(raw_event.get("reasoning_details")))
            if reasoning_text:
                event = _normalized_event_base(
                    agent_type="hermes",
                    turn_id=turn_id,
                    session_id=event_session_id,
                    event_kind="thinking",
                    raw_event=raw_event,
                )
                event["text"] = reasoning_text
                normalized.append(event)

            tool_calls = _json_loads_maybe(raw_event.get("tool_calls"))
            if isinstance(tool_calls, dict):
                if isinstance(tool_calls.get("tool_calls"), list):
                    tool_calls = tool_calls["tool_calls"]
                else:
                    tool_calls = [tool_calls]
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    tool_name, tool_input = _tool_call_name_and_input(tool_call)
                    event = _normalized_event_base(
                        agent_type="hermes",
                        turn_id=turn_id,
                        session_id=event_session_id,
                        event_kind="tool_call",
                        raw_event=raw_event,
                    )
                    event["tool_call_id"] = tool_call.get("id") or tool_call.get("tool_call_id")
                    event["tool_name"] = tool_name
                    event["tool_input"] = tool_input
                    normalized.append(event)

            text = _content_text(content)
            if text:
                event = _normalized_event_base(
                    agent_type="hermes",
                    turn_id=turn_id,
                    session_id=event_session_id,
                    event_kind="assistant_text",
                    raw_event=raw_event,
                )
                event["text"] = text
                normalized.append(event)
            continue

        if role in {"tool", "tool_result", "function"}:
            text = _content_text(content)
            event = _normalized_event_base(
                agent_type="hermes",
                turn_id=turn_id,
                session_id=event_session_id,
                event_kind="tool_result",
                raw_event=raw_event,
            )
            event["tool_call_id"] = raw_event.get("tool_call_id")
            event["tool_name"] = raw_event.get("tool_name") or raw_event.get("name")
            event["text"] = text
            event["tool_output"] = text
            normalized.append(event)
    return normalized
