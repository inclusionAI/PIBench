from typing import Any, Dict, List

from payskills_runtime.agent.events.schema import _normalized_event_base


def _message_content(event: Dict[str, Any]) -> List[Any]:
    message = event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = event.get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def normalize_claude_event(raw_event: Dict[str, Any], turn_id: str, session_id: str) -> List[Dict[str, Any]]:
    event_type = str(raw_event.get("type") or "")
    events: List[Dict[str, Any]] = []

    if event_type == "system":
        event = _normalized_event_base(
            agent_type="claude-code",
            turn_id=turn_id,
            session_id=str(raw_event.get("session_id") or session_id),
            event_kind="session",
            raw_event=raw_event,
        )
        event["subtype"] = raw_event.get("subtype")
        events.append(event)
        return events

    if event_type == "result":
        event = _normalized_event_base(
            agent_type="claude-code",
            turn_id=turn_id,
            session_id=str(raw_event.get("session_id") or session_id),
            event_kind="final_result",
            raw_event=raw_event,
        )
        event["subtype"] = raw_event.get("subtype")
        event["text"] = str(raw_event.get("result") or "")
        events.append(event)
        return events

    for block in _message_content(raw_event):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "tool_use":
            event = _normalized_event_base(
                agent_type="claude-code",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="tool_call",
                raw_event=raw_event,
            )
            event["tool_call_id"] = block.get("id")
            event["tool_name"] = block.get("name")
            event["tool_input"] = block.get("input")
            events.append(event)
        elif block_type == "tool_result":
            event = _normalized_event_base(
                agent_type="claude-code",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="tool_result",
                raw_event=raw_event,
            )
            event["tool_call_id"] = block.get("tool_use_id")
            event["text"] = block.get("content")
            event["tool_output"] = block.get("content")
            event["is_error"] = bool(block.get("is_error"))
            events.append(event)
        elif block_type == "text":
            event = _normalized_event_base(
                agent_type="claude-code",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="assistant_text" if event_type == "assistant" else "user_text",
                raw_event=raw_event,
            )
            event["text"] = str(block.get("text") or "")
            events.append(event)
        elif block_type in {"thinking", "redacted_thinking"}:
            event = _normalized_event_base(
                agent_type="claude-code",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="thinking",
                raw_event=raw_event,
            )
            event["text"] = str(block.get("thinking") or block.get("text") or "")
            events.append(event)

    if events:
        return events

    if event_type:
        return [
            _normalized_event_base(
                agent_type="claude-code",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="raw",
                raw_event=raw_event,
            )
        ]
    return []
