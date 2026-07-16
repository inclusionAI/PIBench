import json
from pathlib import Path
from typing import Dict, List

from payskills_runtime.config import config_summary


def numeric_score(score) -> float:
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def task_instance_passed(run_exit: int, evaluation_exit: int, score) -> bool:
    return run_exit == 0 and evaluation_exit == 0 and numeric_score(score) >= 1.0


def build_task_instance_summary(
    task_instance: Dict[str, Path],
    task_instance_log_dir: Path,
    result: Dict,
    run_exit: int,
    evaluation_exit: int,
    *,
    diff_exit=None,
) -> Dict:
    score = result.get("score", 0)
    summary = {
        "task_instance": task_instance["name"],
        "version": task_instance["version"],
        "label": task_instance["label"],
        "project": task_instance.get("project", ""),
        "product": task_instance.get("product", ""),
        "scenario": task_instance.get("scenario", ""),
        "score": score,
        "passed": task_instance_passed(run_exit, evaluation_exit, score),
        "run_exit": run_exit,
        "evaluation_exit": evaluation_exit,
        "summary": result.get("summary", ""),
        "log_dir": str(task_instance_log_dir),
    }
    if diff_exit is not None:
        summary["diff_exit"] = diff_exit
    return summary


def build_run_summary(run_id: str, config: Dict, task_instance_summaries: List[Dict]) -> Dict:
    passed = sum(1 for task_instance in task_instance_summaries if task_instance.get("passed"))
    failed = len(task_instance_summaries) - passed
    return {
        "schema_version": 1,
        "run_id": run_id,
        "total": len(task_instance_summaries),
        "passed": passed,
        "failed": failed,
        "config": config_summary(config),
        "task_instances": task_instance_summaries,
    }


def write_run_summary(run_root: Path, summary: Dict) -> None:
    (run_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
