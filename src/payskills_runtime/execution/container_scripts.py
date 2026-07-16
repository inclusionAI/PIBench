import os
import subprocess
from pathlib import Path
from typing import Dict

from payskills_runtime.diff import export_workspace_diff, init_workspace_git
from payskills_runtime.execution import standard_artifacts_dir, standard_logs_dir


def runtime_env(task_instance_dir: Path, output_dir: Path, workspace: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TASK_INSTANCE_DIR": str(task_instance_dir),
            "OUTPUT_DIR": str(output_dir),
            "PAYSKILLS_ARTIFACTS_DIR": str(standard_artifacts_dir(output_dir)),
            "PAYSKILLS_LOGS_DIR": str(standard_logs_dir(output_dir)),
            "WORKSPACE": str(workspace),
            "WORKDIR": str(workspace),
            "PAYSKILLS_RUNTIME": env.get("PAYSKILLS_RUNTIME", "kit"),
            "PAYSKILLS_RUNTIME_DIR": env.get("PAYSKILLS_RUNTIME_DIR", "/opt/payskills_runtime"),
        }
    )
    return env


def run_logged_script(
    script: Path,
    task_instance_dir: Path,
    output_dir: Path,
    workspace: Path,
    log_path: Path,
    timeout_sec: int,
) -> int:
    if not script.exists():
        log_path.write_text("missing script: {0}\n".format(script), encoding="utf-8")
        return 127

    env = runtime_env(task_instance_dir, output_dir, workspace)
    with log_path.open("w", encoding="utf-8") as log_file:
        try:
            proc = subprocess.run(
                ["bash", str(script)],
                cwd=str(workspace),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            log_file.write("\nscript timed out after {0}s\n".format(timeout_sec))
            return 124
    return int(proc.returncode)


def init_baseline(workspace: Path, output_dir: Path) -> None:
    try:
        init_workspace_git(workspace)
    except Exception as exc:
        standard_logs_dir(output_dir).mkdir(parents=True, exist_ok=True)
        (standard_logs_dir(output_dir) / "diff_init_error.txt").write_text(
            "failed to initialize workspace git baseline: {0}\n".format(exc),
            encoding="utf-8",
        )


def export_diff(workspace: Path, output_dir: Path) -> int:
    try:
        export_workspace_diff(workspace, standard_artifacts_dir(output_dir))
        return 0
    except Exception as exc:
        standard_logs_dir(output_dir).mkdir(parents=True, exist_ok=True)
        (standard_logs_dir(output_dir) / "diff_export_error.txt").write_text(
            "failed to export workspace diff: {0}\n".format(exc),
            encoding="utf-8",
        )
        return 1
