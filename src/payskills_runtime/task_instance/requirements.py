import re
from pathlib import Path
from typing import Dict, Iterable, Set


SCRIPT_REL_PATHS = ("task/run.sh", "evaluation/evaluate.sh")
HELPER_REQUIREMENTS = {
    "payskills-agent": "agent",
    "payskills-judge": "judge",
}


def _contains_helper(text: str, helper: str) -> bool:
    pattern = r"(^|[^A-Za-z0-9_.-]){0}($|[^A-Za-z0-9_.-])".format(re.escape(helper))
    return re.search(pattern, text) is not None


def _script_body(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def task_instance_requirements(task_instance: Dict) -> Set[str]:
    task_instance_dir = Path(task_instance["path"])
    requirements: Set[str] = set()
    for rel_path in SCRIPT_REL_PATHS:
        script_path = task_instance_dir / rel_path
        try:
            text = script_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _script_body(text)
        for helper, requirement in HELPER_REQUIREMENTS.items():
            if _contains_helper(text, helper):
                requirements.add(requirement)
    return requirements


def selected_task_instance_requirements(task_instances: Iterable[Dict]) -> Set[str]:
    requirements: Set[str] = set()
    for task_instance in task_instances:
        requirements.update(task_instance_requirements(task_instance))
    return requirements
