import shutil
from pathlib import Path
from typing import Dict

from payskills_runtime.task_instance import task_instance_run_script, task_instance_evaluation_script
from payskills_runtime.task_instance.execution import TaskInstanceExecutionSpec, execute_task_instance
from payskills_runtime.docker.commands import docker_enabled
from payskills_runtime.docker.host import run_task_instance_in_docker
from payskills_runtime.execution import (
    ensure_standard_output_dirs,
    execution_phase_exit,
    load_result,
    prepare_workspace,
)
from payskills_runtime.execution.runtime_env import runtime_env_from_config
from payskills_runtime.execution.runtime_inputs import (
    container_runtime_input_env,
    copy_runtime_inputs_to_workspace,
    prepare_runtime_inputs,
)
from payskills_runtime.execution.summary import build_task_instance_summary


def run_task_instance(task_instance: Dict[str, Path], run_root: Path, kit_dir: Path, config: Dict) -> Dict:
    task_instance_dir = Path(task_instance["path"])
    label = str(task_instance.get("label") or task_instance["name"]).strip("/")
    task_instance_log_dir = run_root.joinpath(*[part for part in label.split("/") if part])
    output_dir = task_instance_log_dir
    workspace_dir = task_instance_log_dir / "workspace"
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_standard_output_dirs(output_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    prepare_workspace(task_instance_dir, workspace_dir)
    runtime_env = runtime_env_from_config(config)
    prepared_runtime_inputs = prepare_runtime_inputs(task_instance_dir, config, output_dir=output_dir)
    copy_runtime_inputs_to_workspace(prepared_runtime_inputs, workspace_dir)

    try:
        if docker_enabled(config):
            runtime_env.update(container_runtime_input_env(prepared_runtime_inputs))
            run_exit, evaluation_exit = run_task_instance_in_docker(
                task_instance,
                task_instance_dir,
                task_instance_log_dir,
                output_dir,
                workspace_dir,
                kit_dir,
                config,
                runtime_env,
                runtime_input_mounts=prepared_runtime_inputs.mounts,
            )
            diff_exit = execution_phase_exit(output_dir, "diff", 127)
        else:
            runtime_env.update(prepared_runtime_inputs.env)
            timeout_sec = int(config.get("run", {}).get("timeout_sec") or 3600)
            executed = execute_task_instance(
                TaskInstanceExecutionSpec(
                    task_instance_dir=task_instance_dir,
                    output_dir=output_dir,
                    workspace_dir=workspace_dir,
                    kit_dir=kit_dir,
                    run_script=task_instance_run_script(task_instance_dir).relative_to(task_instance_dir),
                    evaluation_script=task_instance_evaluation_script(task_instance_dir).relative_to(task_instance_dir),
                    runtime_env=runtime_env,
                    timeout_sec=timeout_sec,
                    task_instance=task_instance,
                )
            )
            run_exit = executed.run_exit
            diff_exit = executed.diff_exit
            evaluation_exit = executed.evaluation_exit
    finally:
        for path in prepared_runtime_inputs.cleanup_paths:
            shutil.rmtree(path, ignore_errors=True)
    result = load_result(output_dir)
    summary = build_task_instance_summary(
        task_instance,
        task_instance_log_dir,
        result,
        run_exit,
        evaluation_exit,
        diff_exit=diff_exit,
    )
    return summary
