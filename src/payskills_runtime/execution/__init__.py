import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from payskills_runtime.diff import export_workspace_diff, init_workspace_git


TIMEOUT_EXIT_CODES = {124, 137}
EXECUTION_SCHEMA_VERSION = "payskills-execution/v1"

AGENT_ARTIFACT_NAMES = (
    "agent_input.txt",
    "agent_output.txt",
    "agent_usage.json",
    "agent_events.jsonl",
    "agent_evidence.json",
    "agent_trace.json",
    "agent_run.json",
    "agent_status.txt",
    "agent_runtime_doctor.json",
)
DIFF_ARTIFACT_NAMES = ("patch.diff", "changed_files.txt")
ARTIFACT_DIR_NAMES = ("code_files", "turns")


def standard_logs_dir(output_dir: Path) -> Path:
    return Path(output_dir) / "logs"


def standard_artifacts_dir(output_dir: Path) -> Path:
    return Path(output_dir) / "artifacts"


def ensure_standard_output_dirs(output_dir: Path) -> Dict[str, Path]:
    output_path = Path(output_dir)
    logs_dir = standard_logs_dir(output_path)
    artifacts_dir = standard_artifacts_dir(output_path)
    logs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return {"root": output_path, "logs": logs_dir, "artifacts": artifacts_dir}


def _relative(output_dir: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(output_dir).resolve()))
    except Exception:
        return str(path)


def standard_artifact_paths(output_dir: Path) -> Dict[str, str]:
    root = Path(output_dir)
    return {
        "agent_input": _relative(root, standard_artifacts_dir(root) / "agent_input.txt"),
        "agent_output": _relative(root, standard_artifacts_dir(root) / "agent_output.txt"),
        "agent_usage": _relative(root, standard_artifacts_dir(root) / "agent_usage.json"),
        "agent_trace": _relative(root, standard_artifacts_dir(root) / "agent_trace.json"),
        "agent_events": _relative(root, standard_artifacts_dir(root) / "agent_events.jsonl"),
        "agent_evidence": _relative(root, standard_artifacts_dir(root) / "agent_evidence.json"),
        "patch": _relative(root, standard_artifacts_dir(root) / "patch.diff"),
        "changed_files": _relative(root, standard_artifacts_dir(root) / "changed_files.txt"),
        "code_files": _relative(root, standard_artifacts_dir(root) / "code_files"),
    }


def standard_log_paths(output_dir: Path) -> Dict[str, str]:
    root = Path(output_dir)
    logs_dir = standard_logs_dir(root)
    return {
        "run": _relative(root, logs_dir / "run_stdout.log"),
        "diff": _relative(root, logs_dir / "diff_export.log"),
        "evaluation": _relative(root, logs_dir / "evaluation_output.txt"),
        "agent_runtime_doctor": _relative(root, logs_dir / "agent_runtime_doctor.log"),
        "git_init": _relative(root, logs_dir / "git_init.log"),
        "prepare_skills": _relative(root, logs_dir / "prepare_skills.log"),
        "docker_build": _relative(root, logs_dir / "docker_build.log"),
        "docker_stdout": _relative(root, logs_dir / "docker_stdout.log"),
        "result_validate": _relative(root, logs_dir / "result_validate.log"),
    }


def phase_status(exit_code: Optional[int]) -> str:
    if exit_code is None:
        return "not_run"
    if int(exit_code) == 0:
        return "passed"
    if int(exit_code) in TIMEOUT_EXIT_CODES:
        return "timeout"
    return "failed"


def _phase(name: str, exit_code: Optional[int], log_path: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": phase_status(exit_code), "log": log_path}
    payload["exit_code"] = int(exit_code) if exit_code is not None else None
    return payload


def build_execution_manifest(
    *,
    task_instance: Mapping[str, Any],
    result: Mapping[str, Any],
    run_exit: Optional[int],
    diff_exit: Optional[int],
    evaluation_exit: Optional[int],
    metadata: Optional[Mapping[str, Any]] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(output_dir or ".")
    logs = standard_log_paths(root)
    return {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "runtime": "payskills-runtime-kit",
        "task_instance": {
            "id": task_instance.get("id") or task_instance.get("name") or "",
            "name": task_instance.get("name") or task_instance.get("id") or "",
            "version": task_instance.get("version") or "",
            "label": task_instance.get("label") or task_instance.get("name") or "",
        },
        "metadata": dict(metadata or {}),
        "result": {
            "score": result.get("score", 0),
            "max_score": result.get("max_score", 1),
            "summary": result.get("summary", ""),
        },
        "phases": {
            "run": _phase("run", run_exit, logs["run"]),
            "diff": _phase("diff", diff_exit, logs["diff"]),
            "evaluation": _phase("evaluation", evaluation_exit, logs["evaluation"]),
        },
        "paths": {
            "result": "result.json",
            "logs": logs,
            "artifacts": standard_artifact_paths(root),
        },
    }


def write_execution_manifest(output_dir: Path, manifest: Mapping[str, Any]) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "execution.json").write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_execution_manifest(output_dir: Path) -> Dict[str, Any]:
    try:
        payload = json.loads((Path(output_dir) / "execution.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def execution_phase_exit(output_dir: Path, phase: str, default: int) -> int:
    manifest = load_execution_manifest(output_dir)
    try:
        value = manifest["phases"][phase]["exit_code"]
        return int(value)
    except Exception:
        return int(default)


def write_execution_status(
    output_dir: Path,
    *,
    task_instance: Mapping[str, Any],
    result: Mapping[str, Any],
    run_exit: Optional[int],
    diff_exit: Optional[int],
    evaluation_exit: Optional[int],
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_standard_output_dirs(output_dir)
    manifest = build_execution_manifest(
        task_instance=task_instance,
        result=result,
        run_exit=run_exit,
        diff_exit=diff_exit,
        evaluation_exit=evaluation_exit,
        metadata=metadata,
        output_dir=output_dir,
    )
    write_execution_manifest(output_dir, manifest)
    return manifest


def _move_if_present(source: Path, target: Path) -> None:
    if not source.exists() or source == target:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
    shutil.move(str(source), str(target))


def standardize_output_layout(output_dir: Path) -> None:
    output_path = Path(output_dir)
    dirs = ensure_standard_output_dirs(output_path)
    artifacts_dir = dirs["artifacts"]
    for name in AGENT_ARTIFACT_NAMES + DIFF_ARTIFACT_NAMES:
        _move_if_present(output_path / name, artifacts_dir / name)
    for name in ARTIFACT_DIR_NAMES:
        _move_if_present(output_path / name, artifacts_dir / name)
    for pattern in ("*.prompt.md", "*.prompt.txt"):
        for prompt_file in sorted(output_path.glob(pattern)):
            _move_if_present(prompt_file, artifacts_dir / prompt_file.name)


def run_script(
    script: Path,
    task_instance_dir: Path,
    output_dir: Path,
    workspace_dir: Path,
    kit_dir: Path,
    log_path: Path,
    runtime_env: Dict[str, str],
    timeout_sec: int,
) -> int:
    if not script.exists():
        log_path.write_text("missing script: {0}\n".format(script), encoding="utf-8")
        return 127

    env = os.environ.copy()
    env.update(
        {
            "TASK_INSTANCE_DIR": str(task_instance_dir),
            "OUTPUT_DIR": str(output_dir),
            "PAYSKILLS_ARTIFACTS_DIR": str(standard_artifacts_dir(output_dir)),
            "PAYSKILLS_LOGS_DIR": str(standard_logs_dir(output_dir)),
            "WORKSPACE": str(workspace_dir),
            "WORKDIR": str(workspace_dir),
            "PAYSKILLS_RUNTIME": "kit",
            "PAYSKILLS_RUNTIME_DIR": str(kit_dir),
            "PATH": "{0}:{1}".format(kit_dir / "bin", env.get("PATH", "")),
            "PYTHONPATH": "{0}{1}{2}".format(
                kit_dir,
                os.pathsep if env.get("PYTHONPATH") else "",
                env.get("PYTHONPATH", ""),
            ),
        }
    )
    env.update(runtime_env)

    with log_path.open("w", encoding="utf-8") as log_file:
        try:
            proc = subprocess.run(
                ["bash", str(script)],
                cwd=str(workspace_dir),
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


def load_result(output_dir: Path) -> Dict:
    result_path = output_dir / "result.json"
    if not result_path.exists():
        return {
            "score": 0,
            "max_score": 1,
            "summary": "result.json missing",
            "rubrics": [],
        }
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "score": 0,
            "max_score": 1,
            "summary": "invalid result.json: {0}".format(exc),
            "rubrics": [],
        }
    return result if isinstance(result, dict) else {"score": 0, "max_score": 1, "summary": "result.json is not an object"}


def prepare_workspace(task_instance_dir: Path, workspace_dir: Path) -> None:
    for project_dir in (
        task_instance_dir / "task" / "fixtures" / "project",
        task_instance_dir / "task" / "fixture" / "project",
        task_instance_dir / "fixtures" / "project",
    ):
        if project_dir.is_dir():
            copy_tree_contents(project_dir, workspace_dir)
            return


def copy_tree_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            copy_tree_contents(item, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(destination))


def init_workspace_baseline(workspace_dir: Path, output_dir: Path) -> None:
    ensure_standard_output_dirs(output_dir)
    try:
        init_workspace_git(workspace_dir)
    except Exception as exc:
        (standard_logs_dir(output_dir) / "diff_init_error.txt").write_text(
            "failed to initialize workspace git baseline: {0}\n".format(exc),
            encoding="utf-8",
        )


def export_workspace_diff_artifacts(workspace_dir: Path, output_dir: Path) -> int:
    artifacts_dir = standard_artifacts_dir(output_dir)
    try:
        export_workspace_diff(workspace_dir, artifacts_dir)
        return 0
    except Exception as exc:
        (standard_logs_dir(output_dir) / "diff_export_error.txt").write_text(
            "failed to export workspace diff: {0}\n".format(exc),
            encoding="utf-8",
        )
        return 1
