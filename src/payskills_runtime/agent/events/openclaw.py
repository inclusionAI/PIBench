from typing import Any, Dict, List

from payskills_runtime.agent.events.parsing import _content_blocks, _content_text, _tool_call_name_and_input
from payskills_runtime.agent.events.schema import _normalized_event_base


def normalize_openclaw_provider_events(records: List[Dict[str, Any]], turn_id: str, session_id: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw_event in records:
        event_type = str(raw_event.get("type") or "")
        if event_type == "session":
            event = _normalized_event_base(
                agent_type="openclaw",
                turn_id=turn_id,
                session_id=str(raw_event.get("sessionId") or raw_event.get("session_id") or session_id),
                event_kind="session",
                raw_event=raw_event,
            )
            normalized.append(event)
            continue

        message = raw_event.get("message") if isinstance(raw_event.get("message"), dict) else {}
        role = str(message.get("role") or raw_event.get("role") or "")
        content = message.get("content") if "content" in message else raw_event.get("content")
        if role == "toolResult":
            text = _content_text(content)
            event = _normalized_event_base(
                agent_type="openclaw",
                turn_id=turn_id,
                session_id=session_id,
                event_kind="tool_result",
                raw_event=raw_event,
            )
            event["tool_call_id"] = message.get("toolCallId") or raw_event.get("toolCallId") or raw_event.get("tool_call_id")
            event["text"] = text
            event["tool_output"] = text
            normalized.append(event)
            continue

        for block in _content_blocks(content):
            block_type = str(block.get("type") or "")
            if block_type in {"toolCall", "tool_call", "tool_use"}:
                tool_name, tool_input = _tool_call_name_and_input(block)
                event = _normalized_event_base(
                    agent_type="openclaw",
                    turn_id=turn_id,
                    session_id=session_id,
                    event_kind="tool_call",
                    raw_event=raw_event,
                )
                event["tool_call_id"] = block.get("id") or block.get("toolCallId") or block.get("tool_use_id")
                event["tool_name"] = tool_name
                event["tool_input"] = tool_input
                normalized.append(event)
            elif block_type in {"toolResult", "tool_result"}:
                text = _content_text(block.get("content") if "content" in block else block.get("text"))
                event = _normalized_event_base(
                    agent_type="openclaw",
                    turn_id=turn_id,
                    session_id=session_id,
                    event_kind="tool_result",
                    raw_event=raw_event,
                )
                event["tool_call_id"] = block.get("toolCallId") or block.get("tool_use_id") or message.get("toolCallId")
                event["text"] = text
                event["tool_output"] = text
                event["is_error"] = bool(block.get("isError") or block.get("is_error"))
                normalized.append(event)
            elif block_type in {"thinking", "redacted_thinking"}:
                event = _normalized_event_base(
                    agent_type="openclaw",
                    turn_id=turn_id,
                    session_id=session_id,
                    event_kind="thinking",
                    raw_event=raw_event,
                )
                event["text"] = str(block.get("thinking") or block.get("text") or "")
                normalized.append(event)
            elif block_type == "text":
                text = str(block.get("text") or "")
                if not text:
                    continue
                if role == "assistant":
                    event_kind = "assistant_text"
                elif role == "user":
                    event_kind = "user_message"
                else:
                    event_kind = "raw"
                event = _normalized_event_base(
                    agent_type="openclaw",
                    turn_id=turn_id,
                    session_id=session_id,
                    event_kind=event_kind,
                    raw_event=raw_event,
                )
                event["text"] = text
                normalized.append(event)
    return normalized
