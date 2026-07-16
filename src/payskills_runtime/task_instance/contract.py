from pathlib import Path
from typing import Dict, List


def task_instance_contract_errors(task_instance: Dict) -> List[str]:
    task_instance_dir = Path(task_instance["path"])
    label = str(task_instance.get("label") or task_instance_dir.name)
    errors = []

    if not (task_instance_dir / "task_instance.toml").exists():
        errors.append("task instance {0} is missing task_instance.toml".format(label))
    if not (task_instance_dir / "task").is_dir():
        errors.append("task instance {0} is missing task/ directory".format(label))
    if not (task_instance_dir / "evaluation").is_dir():
        errors.append("task instance {0} is missing evaluation/ directory".format(label))
    if not (task_instance_dir / "evaluation" / "deterministic").is_dir():
        errors.append("task instance {0} is missing evaluation/deterministic/ directory".format(label))
    if not (task_instance_dir / "task" / "Dockerfile").exists():
        errors.append("task instance {0} is missing task/Dockerfile".format(label))
    if not (task_instance_dir / "task" / "run.sh").exists():
        errors.append("task instance {0} is missing task/run.sh".format(label))
    if not (task_instance_dir / "evaluation" / "evaluate.sh").exists():
        errors.append("task instance {0} is missing evaluation/evaluate.sh".format(label))
    if not (task_instance_dir / "evaluation" / "rubrics.json").exists():
        errors.append("task instance {0} is missing evaluation/rubrics.json".format(label))
    if (task_instance_dir / "environment" / "Dockerfile").exists():
        errors.append("task instance {0} uses legacy environment/Dockerfile; move it to task/Dockerfile".format(label))
    if (task_instance_dir / "run.sh").exists():
        errors.append("task instance {0} uses legacy root run.sh; move it to task/run.sh".format(label))
    if (task_instance_dir / "test.sh").exists():
        errors.append("task instance {0} uses legacy root test.sh; move it to evaluation/evaluate.sh".format(label))
    if (task_instance_dir / "test").exists():
        errors.append("task instance {0} uses legacy test/ directory; move it to evaluation/".format(label))
    return errors
