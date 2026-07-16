import sys
from pathlib import Path
from typing import Dict, List, Tuple

from payskills_runtime.task_instance.contract import task_instance_contract_errors
from payskills_runtime.task_instance.requirements import selected_task_instance_requirements
from payskills_runtime.task_instance import discover_task_instances, filter_task_instances
from payskills_runtime.config import load_config, load_config_source
from payskills_runtime.config.contract import config_contract_errors
from payskills_runtime.doctor.guidance import hints_for_errors
from payskills_runtime.export.package import export_package_errors
from payskills_runtime.execution.runtime_checks import validate_runtime_requirements
from payskills_runtime.execution.runtime_inputs import runtime_input_errors


def validate_export_inputs(
    export_root: Path,
    config_path: Path,
    *,
    check_runtime: bool = False,
) -> Tuple[Dict, List[Dict], List[str]]:
    errors = []
    errors.extend(export_package_errors(export_root))

    try:
        config_source = load_config_source(config_path)
    except Exception as exc:
        errors.append("config could not be loaded: {0}".format(exc))
        return {}, [], errors

    config_shape_errors = config_contract_errors(config_source)
    errors.extend(config_shape_errors)
    if config_shape_errors:
        return {}, [], errors

    config = load_config(config_path)
    try:
        task_instances = filter_task_instances(
            discover_task_instances(export_root / "benchmark_suite"),
            config.get("run", {}).get("task_instances", []),
        )
    except SystemExit as exc:
        errors.append(str(exc))
        return config, [], errors

    if not task_instances:
        errors.append("no task instances discovered")

    for task_instance in task_instances:
        errors.extend(task_instance_contract_errors(task_instance))
    if check_runtime and not errors:
        validate_runtime_requirements(config, selected_task_instance_requirements(task_instances), errors)
        errors.extend(runtime_input_errors(task_instances, config))
    return config, task_instances, errors


def print_preflight_errors(errors: List[str], stream=None) -> None:
    if stream is None:
        stream = sys.stderr
    for error in errors:
        print("ERROR {0}".format(error), file=stream)
    for hint in hints_for_errors(errors):
        print("HINT {0}".format(hint), file=stream)
