import json
import re
from pathlib import Path
from typing import Any, Dict, List, Union


def load_turns(path: Union[str, Path]) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    turns = payload.get("turns") if isinstance(payload, dict) else payload
    if not isinstance(turns, list):
        raise ValueError("turns must be a list or an object with a turns list")
    normalized = []
    for index, turn in enumerate(turns, start=1):
        if not isinstance(turn, dict):
            raise ValueError(f"turn {index} must be an object")
        item = dict(turn)
        item.setdefault("id", f"turn-{index}")
        normalized.append(item)
    return normalized


def build_turn_message(
    turn: Dict[str, Any],
    *,
    skill_trigger: str = "",
    skill_name: str = "",
) -> str:
    user = str(turn.get("user") or "")
    blocks = []
    context = turn.get("context")
    if isinstance(context, dict) and context:
        context_lines = [f"{key}: {value}" for key, value in context.items()]
        blocks.append("上下文:\n" + "\n".join(context_lines))
    elif isinstance(context, str) and context.strip():
        blocks.append("上下文:\n" + context.strip())
    blocks.append("用户输入:\n" + user)
    message = "\n\n".join(blocks).strip()
    if skill_trigger == "slash" and skill_name:
        message = f"/{skill_name} {message}"
    return message + "\n"


def build_effective_turn_prompt(
    turn_message: str,
    system_instruction: str,
    *,
    include_system_instruction: bool,
) -> str:
    if not include_system_instruction or not system_instruction.strip():
        return turn_message

    instruction = system_instruction.rstrip()
    body = turn_message.lstrip()
    slash_match = re.match(r"^(/[A-Za-z0-9_.-]+)\s+([\s\S]*)$", body)
    if slash_match:
        prefix, rest = slash_match.groups()
        return f"{prefix} 系统提示词:\n{instruction}\n\n{rest.lstrip().rstrip()}\n"
    return f"系统提示词:\n{instruction}\n\n{body.rstrip()}\n"
