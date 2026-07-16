import json
from typing import Any, Dict, List, Optional, Tuple


def _json_loads_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    try:
        return json.loads(stripped)
    except Exception:
        return value


def _content_blocks(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, dict):
        return [content]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text is None:
                    text = block.get("content")
                if text is not None:
                    parts.append(str(text))
            elif block is not None:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _tool_call_name_and_input(block: Dict[str, Any]) -> Tuple[Optional[str], Any]:
    function = block.get("function") if isinstance(block.get("function"), dict) else {}
    name = block.get("name") or function.get("name")
    tool_input = block.get("input")
    if tool_input is None:
        tool_input = block.get("arguments")
    if tool_input is None:
        tool_input = block.get("args")
    if tool_input is None:
        tool_input = function.get("arguments")
    return str(name) if name else None, _json_loads_maybe(tool_input)


def wrap_raw_event(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"type": "json_value", "value": value}


def parse_raw_events(raw: str) -> Tuple[List[Dict[str, Any]], str]:
    stripped = raw.strip()
    if not stripped:
        return [], "none"
    try:
        payload = json.loads(stripped)
    except Exception:
        pass
    else:
        if isinstance(payload, list):
            return [wrap_raw_event(item) for item in payload], "json"
        return [wrap_raw_event(payload)], "json"

    records: List[Dict[str, Any]] = []
    invalid = 0
    for line_no, line in enumerate(raw.splitlines(), start=1):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        try:
            payload = json.loads(stripped_line)
        except Exception:
            invalid += 1
            records.append({"type": "raw_text", "line": line_no, "text": line})
        else:
            record = wrap_raw_event(payload)
            record.setdefault("_raw_line", line_no)
            records.append(record)
    if invalid and invalid == len(records):
        return records, "text"
    if invalid:
        return records, "mixed"
    return records, "jsonl"
