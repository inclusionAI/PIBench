import concurrent.futures
import sys
from datetime import datetime
from pathlib import Path

from payskills_runtime.task_instance.runner import run_task_instance
from payskills_runtime.execution.preflight import print_preflight_errors, validate_export_inputs
from payskills_runtime.execution.run_output import print_run_complete
from payskills_runtime.execution.run_paths import run_root_for_timestamp
from payskills_runtime.execution.summary import build_run_summary, write_run_summary


def run_exported_task_instances(export_root: Path, config_path: Path) -> int:
    config, task_instances, errors = validate_export_inputs(export_root, config_path, check_runtime=True)
    if errors:
        print_preflight_errors(errors, stream=sys.stderr)
        return 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = run_root_for_timestamp(export_root, config, timestamp)
    run_root.mkdir(parents=True, exist_ok=True)
    kit_dir = Path(__file__).resolve().parents[2]

    parallelism = int(config.get("run", {}).get("parallelism") or 1)
    task_instance_summaries = [None] * len(task_instances)
    if parallelism <= 1 or len(task_instances) <= 1:
        for idx, task_instance in enumerate(task_instances):
            task_instance_summaries[idx] = run_task_instance(task_instance, run_root, kit_dir, config)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism) as executor:
            future_map = {
                executor.submit(run_task_instance, task_instance, run_root, kit_dir, config): idx
                for idx, task_instance in enumerate(task_instances)
            }
            for future in concurrent.futures.as_completed(future_map):
                task_instance_summaries[future_map[future]] = future.result()
    summary = build_run_summary(timestamp, config, task_instance_summaries)
    write_run_summary(run_root, summary)
    print_run_complete(run_root, summary)
    return 0 if summary["failed"] == 0 else 1
