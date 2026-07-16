import json
from typing import Any, Dict, List

from payskills_runtime.agent.events import parse_raw_events


def _text_from_claude_records(records: List[Any]) -> str:
    for item in reversed(records):
        if isinstance(item, dict) and item.get("type") == "result":
            return str(item.get("result") or "")
    text_blocks = []
    for item in records:
        if not isinstance(item, dict):
            continue
        message = item.get("message") if isinstance(item.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    text_blocks.append(str(block.get("text")))
        elif isinstance(content, str):
            text_blocks.append(content)
    if text_blocks:
        return "\n".join(text_blocks)
    return ""


def _text_from_claude_payload(payload: Any) -> str:
    if isinstance(payload, list):
        return _text_from_claude_records(payload)
    if isinstance(payload, dict):
        return str(payload.get("result") or payload.get("message") or "")
    return ""


def _text_from_openclaw_payload(payload: Dict[str, Any]) -> str:
    texts = [
        str(item.get("text") or "")
        for item in payload.get("payloads", [])
        if isinstance(item, dict) and item.get("text")
    ]
    if texts:
        return "\n".join(texts)
    return str(payload.get("result") or payload.get("message") or "")


def extract_visible_output(raw: str, agent_type: str) -> str:
    parsed_records, _parse_kind = parse_raw_events(raw)
    if agent_type == "claude-code" and parsed_records:
        text = _text_from_claude_records(parsed_records)
        if text:
            return text

    try:
        payload = json.loads(raw)
    except Exception:
        return raw
    if agent_type == "claude-code":
        text = _text_from_claude_payload(payload)
        return text if text else raw
    if agent_type == "openclaw" and isinstance(payload, dict):
        return _text_from_openclaw_payload(payload)
    if agent_type == "hermes" and isinstance(payload, dict):
        return str(payload.get("final_response") or payload.get("result") or payload.get("message") or "")
    return raw
