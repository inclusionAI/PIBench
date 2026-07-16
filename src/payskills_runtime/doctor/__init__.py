from pathlib import Path

from payskills_runtime.task_instance import discover_task_instances, filter_task_instances
from payskills_runtime.config import load_config, load_config_source
from payskills_runtime.config.contract import config_contract_errors
from payskills_runtime.doctor.checks import validate_doctor_task_instance_contracts, validate_doctor_runtime_requirements
from payskills_runtime.doctor.output import (
    print_doctor_task_instance_count,
    print_doctor_config_load_error,
    print_doctor_failure,
    print_doctor_header,
    print_doctor_ok,
)
from payskills_runtime.export.package import export_package_errors


def run_doctor(export_root: Path, config_path: Path) -> int:
    print_doctor_header(export_root, config_path)
    errors = []
    warnings = []

    if not config_path.exists():
        warnings.append("config file does not exist; defaults will be used")
    errors.extend(export_package_errors(export_root))

    try:
        config_shape_errors = config_contract_errors(load_config_source(config_path))
        errors.extend(config_shape_errors)
        config = load_config(config_path)
    except Exception as exc:
        print_doctor_config_load_error(exc)
        return 1

    try:
        task_instances = filter_task_instances(
            discover_task_instances(export_root / "benchmark_suite"),
            config.get("run", {}).get("task_instances", []),
        )
    except SystemExit as exc:
        errors.append(str(exc))
        print_doctor_failure(warnings, errors)
        return 1
    print_doctor_task_instance_count(len(task_instances))
    if not task_instances:
        errors.append("no task instances discovered")

    validate_doctor_task_instance_contracts(task_instances, errors)
    validate_doctor_runtime_requirements(
        config,
        task_instances,
        errors,
        config_shape_errors=config_shape_errors,
    )

    if errors:
        print_doctor_failure(warnings, errors)
        return 1
    print_doctor_ok()
    return 0
