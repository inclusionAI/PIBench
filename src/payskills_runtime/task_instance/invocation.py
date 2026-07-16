from pathlib import Path
from typing import Dict, List, Mapping, Union


CONTAINER_TASK_INSTANCE_DIR = "/task_instance"
CONTAINER_WORKSPACE_DIR = "/workspace"
CONTAINER_OUTPUT_DIR = "/output"
CONTAINER_KIT_DIR = "/opt/payskills_runtime"


def container_runtime_env(runtime_env: Mapping[str, str] = None) -> Dict[str, str]:
    env = {
        "TASK_INSTANCE_DIR": CONTAINER_TASK_INSTANCE_DIR,
        "OUTPUT_DIR": CONTAINER_OUTPUT_DIR,
        "WORKSPACE": CONTAINER_WORKSPACE_DIR,
        "WORKDIR": CONTAINER_WORKSPACE_DIR,
        "PAYSKILLS_RUNTIME": "kit",
        "PAYSKILLS_RUNTIME_DIR": CONTAINER_KIT_DIR,
        "PATH": CONTAINER_KIT_DIR + "/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONPATH": CONTAINER_KIT_DIR,
    }
    env.update(dict(runtime_env or {}))
    return env


def container_env_args(runtime_env: Mapping[str, str] = None) -> List[str]:
    args: List[str] = []
    for key, value in sorted(container_runtime_env(runtime_env).items()):
        args.extend(["-e", "{0}={1}".format(key, value)])
    return args


def _path_text(path: Union[str, Path]) -> str:
    return path.as_posix() if isinstance(path, Path) else str(path)


def task_instance_core_args(
    *,
    task_instance_dir: Union[str, Path],
    workspace: Union[str, Path],
    output_dir: Union[str, Path],
    kit_dir: Union[str, Path],
    run_script: Union[str, Path],
    evaluation_script: Union[str, Path],
    timeout_sec: int,
    task_instance_id: str,
    suite_version: str,
    task_instance_label: str,
) -> List[str]:
    return [
        "payskills-run",
        "task-instance-core",
        "--task-instance-dir",
        _path_text(task_instance_dir),
        "--workspace",
        _path_text(workspace),
        "--output-dir",
        _path_text(output_dir),
        "--kit-dir",
        _path_text(kit_dir),
        "--run-script",
        _path_text(run_script),
        "--evaluation-script",
        _path_text(evaluation_script),
        "--timeout-sec",
        str(max(1, int(timeout_sec or 3600))),
        "--task-instance-id",
        str(task_instance_id or ""),
        "--suite-version",
        str(suite_version or ""),
        "--task-instance-label",
        str(task_instance_label or task_instance_id or ""),
    ]
