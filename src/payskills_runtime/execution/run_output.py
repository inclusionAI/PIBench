import sys
from pathlib import Path
from typing import Dict, List


def _dry_run_next_steps(requirements: List[str]) -> List[str]:
    steps = []
    if "agent" in requirements:
        steps.append("fill agent.type and agent.model in config/config.yaml before running agent task instances")
    if "judge" in requirements:
        steps.append(
            "fill judge.base_url, judge.model, and judge.api_key_env in config/config.yaml before running judge task instances"
        )
    steps.append("run ./run.sh --doctor to validate local commands, credentials, and Docker readiness")
    return steps


def print_run_complete(run_root: Path, summary: Dict, stream=None) -> None:
    if stream is None:
        stream = sys.stdout
    print("PaySkills exported benchmark suite run complete", file=stream)
    print("run: {0}".format(run_root), file=stream)
    print("summary: {0}".format(run_root / "summary.json"), file=stream)
    task_instances = summary.get("task_instances") or []
    if task_instances:
        print("task_instance_artifacts:", file=stream)
        for task_instance in task_instances:
            label = task_instance.get("label") or task_instance.get("task_instance") or "task_instance"
            log_dir = Path(str(task_instance.get("log_dir") or run_root / label))
            artifacts = (
                log_dir / "result.json",
                log_dir / "execution.json",
                log_dir / "logs" / "run_stdout.log",
                log_dir / "logs" / "evaluation_output.txt",
            )
            print("- {0}: {1}".format(label, ", ".join(str(path) for path in artifacts)), file=stream)
        failed = [
            task_instance.get("label") or task_instance.get("task_instance") or "task_instance"
            for task_instance in task_instances
            if not task_instance.get("passed")
        ]
        if failed:
            print("failed_task_instances:", file=stream)
            for label in failed:
                print("- {0}".format(label), file=stream)
    print("passed: {0}/{1}".format(summary["passed"], summary["total"]), file=stream)


def print_dry_run_summary(
    export_root: Path,
    config_path: Path,
    package_name: str,
    config: Dict,
    output_root: Path,
    task_instances: List[Dict],
    requirements: List[str],
    stream=None,
) -> None:
    if stream is None:
        stream = sys.stdout
    print("PaySkills exported benchmark suite dry run", file=stream)
    print("root: {0}".format(export_root), file=stream)
    print("config: {0}".format(config_path), file=stream)
    print("name: {0}".format(package_name), file=stream)
    print("parallelism: {0}".format(config.get("run", {}).get("parallelism", 1)), file=stream)
    print("output_dir: {0}".format(output_root), file=stream)
    print("task_instances: {0}".format(len(task_instances)), file=stream)
    print("requirements: {0}".format(", ".join(requirements) if requirements else "none"), file=stream)
    for task_instance in task_instances:
        print("- {0}".format(task_instance["label"]), file=stream)
    print("next:", file=stream)
    for step in _dry_run_next_steps(requirements):
        print("- {0}".format(step), file=stream)
