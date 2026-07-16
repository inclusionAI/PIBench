import sys
from pathlib import Path

from payskills_runtime.task_instance.requirements import selected_task_instance_requirements
from payskills_runtime.common.manifest_contract import load_manifest
from payskills_runtime.execution.preflight import print_preflight_errors, validate_export_inputs
from payskills_runtime.execution.run_output import print_dry_run_summary
from payskills_runtime.execution.run_paths import resolve_output_root


def run_dry_run(export_root: Path, config_path: Path) -> int:
    config, task_instances, errors = validate_export_inputs(export_root, config_path)
    if errors:
        print_preflight_errors(errors, stream=sys.stderr)
        return 1
    manifest = load_manifest(export_root)
    requirements = sorted(selected_task_instance_requirements(task_instances))
    print_dry_run_summary(
        export_root,
        config_path,
        str(manifest.get("name", export_root.name)),
        config,
        resolve_output_root(export_root, config),
        task_instances,
        requirements,
    )
    return 0
