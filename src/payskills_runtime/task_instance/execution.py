import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional

from payskills_runtime.execution import (
    ensure_standard_output_dirs,
    export_workspace_diff_artifacts,
    init_workspace_baseline,
    load_result,
    run_script,
    standard_logs_dir,
    standardize_output_layout,
    write_execution_status,
)
from payskills_runtime.task_instance import task_instance_runtime_env


@dataclass(frozen=True)
class TaskInstanceExecutionSpec:
    task_instance_dir: Path
    workspace_dir: Path
    output_dir: Path
    kit_dir: Path
    run_script: Path
    evaluation_script: Path
    timeout_sec: int
    task_instance: Mapping[str, Any]
    runtime_env: Mapping[str, str] = field(default_factory=dict)
    metadata: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class TaskInstanceExecutionResult:
    run_exit: int
    diff_exit: int
    evaluation_exit: int
    result: Mapping[str, Any]
    execution: Mapping[str, Any]


def _script_path(task_instance_dir: Path, script: Path) -> Path:
    script_path = Path(script)
    return script_path if script_path.is_absolute() else task_instance_dir / script_path


def execute_task_instance(spec: TaskInstanceExecutionSpec) -> TaskInstanceExecutionResult:
    task_instance_dir = Path(spec.task_instance_dir).resolve()
    workspace_dir = Path(spec.workspace_dir).resolve()
    output_dir = Path(spec.output_dir).resolve()
    kit_dir = Path(spec.kit_dir).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_standard_output_dirs(output_dir)
    logs_dir = standard_logs_dir(output_dir)
    runtime_env = dict(spec.runtime_env)
    runtime_env.update(task_instance_runtime_env(task_instance_dir, spec.task_instance))

    init_workspace_baseline(workspace_dir, output_dir)
    run_exit = run_script(
        _script_path(task_instance_dir, spec.run_script),
        task_instance_dir,
        output_dir,
        workspace_dir,
        kit_dir,
        logs_dir / "run_stdout.log",
        runtime_env,
        int(spec.timeout_sec),
    )
    standardize_output_layout(output_dir)
    diff_exit = export_workspace_diff_artifacts(workspace_dir, output_dir)
    evaluation_exit = run_script(
        _script_path(task_instance_dir, spec.evaluation_script),
        task_instance_dir,
        output_dir,
        workspace_dir,
        kit_dir,
        logs_dir / "evaluation_output.txt",
        runtime_env,
        int(spec.timeout_sec),
    )
    standardize_output_layout(output_dir)
    result = load_result(output_dir)
    execution = write_execution_status(
        output_dir,
        task_instance=spec.task_instance,
        result=result,
        run_exit=run_exit,
        diff_exit=diff_exit,
        evaluation_exit=evaluation_exit,
        metadata=spec.metadata,
    )
    return TaskInstanceExecutionResult(
        run_exit=run_exit,
        diff_exit=diff_exit,
        evaluation_exit=evaluation_exit,
        result=result,
        execution=execution,
    )


def run_task_instance_core(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="payskills-run task-instance-core")
    parser.add_argument("--task-instance-dir", default="/task_instance")
    parser.add_argument("--workspace", default="/workspace")
    parser.add_argument("--output-dir", default="/output")
    parser.add_argument("--kit-dir", default="")
    parser.add_argument("--run-script", required=True)
    parser.add_argument("--evaluation-script", required=True)
    parser.add_argument("--timeout-sec", type=int, default=3600)
    parser.add_argument("--task-instance-id", default="")
    parser.add_argument("--suite-version", default="")
    parser.add_argument("--task-instance-label", default="")
    args = parser.parse_args(argv)

    kit_dir = Path(args.kit_dir).resolve() if args.kit_dir else Path(__file__).resolve().parents[2]
    task_instance_id = args.task_instance_id or Path(args.task_instance_dir).name
    execute_task_instance(
        TaskInstanceExecutionSpec(
            task_instance_dir=Path(args.task_instance_dir),
            workspace_dir=Path(args.workspace),
            output_dir=Path(args.output_dir),
            kit_dir=kit_dir,
            run_script=Path(args.run_script),
            evaluation_script=Path(args.evaluation_script),
            timeout_sec=max(1, int(args.timeout_sec or 3600)),
            task_instance={
                "name": task_instance_id,
                "version": args.suite_version,
                "label": args.task_instance_label or task_instance_id,
            },
        )
    )
    return 0
