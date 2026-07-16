import json
from pathlib import Path
from typing import Dict, List, Tuple


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value == "[]":
        return []
    if value == "{}":
        return {}
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def strip_comment(line: str) -> str:
    quote = ""
    for idx, char in enumerate(line):
        if char in {"'", '"'}:
            quote = "" if quote == char else char if not quote else quote
        if char == "#" and not quote and (idx == 0 or line[idx - 1].isspace()):
            return line[:idx]
    return line


def _content_lines(text: str) -> List[Tuple[int, str, str]]:
    lines = []
    for raw_line in text.splitlines():
        line = strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append((indent, line.strip(), raw_line))
    return lines


def _next_nested_container(lines: List[Tuple[int, str, str]], index: int, indent: int):
    for next_indent, next_item, _ in lines[index + 1 :]:
        if next_indent <= indent:
            break
        return [] if next_item.startswith("- ") else {}
    return {}


def parse_simple_yaml(text: str) -> Dict:
    """Parse the small YAML subset used by exported config.yaml."""
    lines = _content_lines(text)
    data: Dict = {}
    stack: List[Tuple[int, object]] = [(-1, data)]

    for index, (indent, item, raw_line) in enumerate(lines):
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError("unsupported config indentation: {0}".format(raw_line))
        parent = stack[-1][1]

        if item.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("list item without list parent: {0}".format(raw_line))
            parent.append(parse_scalar(item[2:]))
            continue

        if ":" not in item:
            raise ValueError("unsupported config line: {0}".format(raw_line))
        if not isinstance(parent, dict):
            raise ValueError("mapping item without mapping parent: {0}".format(raw_line))

        key, value = item.split(":", 1)
        key = key.strip()
        if value.strip():
            parent[key] = parse_scalar(value)
            continue

        child = _next_nested_container(lines, index, indent)
        parent[key] = child
        stack.append((indent, child))
    return data


def load_config_source(config_path: Path) -> Dict:
    config_path = Path(config_path)
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    if config_path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = parse_simple_yaml(text)
    if not isinstance(loaded, dict):
        raise ValueError("config must be an object")
    return loaded
