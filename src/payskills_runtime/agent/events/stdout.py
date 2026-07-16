from typing import Any, Dict, List

from payskills_runtime.agent.events.schema import _normalized_event_base


def normalize_stdout_event(
    raw_event: Dict[str, Any],
    *,
    agent_type: str,
    turn_id: str,
    session_id: str,
) -> List[Dict[str, Any]]:
    event = _normalized_event_base(
        agent_type=agent_type,
        turn_id=turn_id,
        session_id=session_id,
        event_kind="raw",
        raw_event=raw_event,
    )
    payloads = raw_event.get("payloads")
    if isinstance(payloads, list):
        texts = [
            str(item.get("text") or "")
            for item in payloads
            if isinstance(item, dict) and item.get("text")
        ]
        if texts:
            event["event_kind"] = "final_result"
            event["text"] = "\n".join(texts)
            return [event]
    for key in ("result", "message", "final_response", "text", "output"):
        value = raw_event.get(key)
        if value:
            event["text"] = value
            if key in {"result", "final_response", "output"}:
                event["event_kind"] = "final_result"
            break
    if raw_event.get("type") == "raw_text":
        event["text"] = raw_event.get("text")
    return [event]


def visible_final_result_event(agent_type: str, turn_id: str, session_id: str, visible: str) -> Dict[str, Any]:
    raw_event = {
        "type": "visible_output",
        "text": visible,
        "_source": "stdout_visible",
    }
    event = _normalized_event_base(
        agent_type=agent_type,
        turn_id=turn_id,
        session_id=session_id,
        event_kind="final_result",
        raw_event=raw_event,
    )
    event["text"] = visible
    return event
