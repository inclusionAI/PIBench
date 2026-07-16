from pathlib import Path
from typing import Dict, Iterable, List

from payskills_runtime.task_instance import task_instance_run_script, task_instance_evaluation_script
from payskills_runtime.task_instance.contract import task_instance_contract_errors
from payskills_runtime.task_instance.requirements import selected_task_instance_requirements
from payskills_runtime.execution.runtime_checks import validate_host_commands, validate_runtime_requirements
from payskills_runtime.execution.runtime_inputs import runtime_input_errors


def validate_doctor_task_instance_contracts(task_instances: Iterable[Dict], errors: List[str]) -> None:
    for task_instance in task_instances:
        task_instance_dir = Path(task_instance["path"])
        errors.extend(task_instance_contract_errors(task_instance))
        if not task_instance_run_script(task_instance_dir).exists():
            errors.append("missing run script for {0}".format(task_instance["label"]))
        if not task_instance_evaluation_script(task_instance_dir).exists():
            errors.append("missing evaluation script for {0}".format(task_instance["label"]))


def validate_doctor_runtime_requirements(
    config: Dict,
    task_instances: Iterable[Dict],
    errors: List[str],
    *,
    config_shape_errors: List[str],
) -> None:
    validate_host_commands(errors)
    if config_shape_errors:
        return
    task_instance_list = list(task_instances)
    requirements = selected_task_instance_requirements(task_instance_list)
    validate_runtime_requirements(config, requirements, errors, check_host_commands=False)
    errors.extend(runtime_input_errors(task_instance_list, config))
