import os
from pathlib import Path
from typing import Any, Dict


AGENT_COMMANDS = {
    "claude-code": ("claude",),
    "openclaw": ("openclaw",),
    "hermes": ("hermes",),
    "all": ("claude", "openclaw", "hermes"),
}


def find_executable(name: str) -> str:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        path = Path(directory) / name
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if is_file and os.access(str(path), os.X_OK):
            return str(path)
    return ""


def agent_doctor_status(agent_type: str = "") -> Dict[str, Any]:
    selected = (agent_type or os.environ.get("AGENT_TYPE") or os.environ.get("PAYSKILLS_AGENT_TYPE") or "all").strip()
    commands = AGENT_COMMANDS.get(selected)
    if commands is None:
        return {
            "ok": False,
            "agent_type": selected,
            "agents": [],
            "error": "unsupported agent type: {0}".format(selected),
        }
    agents = []
    for name in commands:
        path = find_executable(name)
        agents.append({"name": name, "path": path, "ok": bool(path)})
    return {"ok": all(item["ok"] for item in agents), "agent_type": selected, "agents": agents}
