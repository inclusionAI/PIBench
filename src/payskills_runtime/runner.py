import argparse
import sys
from pathlib import Path

from payskills_runtime.task_instance.execution import run_task_instance_core
from payskills_runtime.docker.images import run_build_task_instance_image, run_build_runtime_image
from payskills_runtime.doctor import run_doctor
from payskills_runtime.execution.dry_run import run_dry_run
from payskills_runtime.execution.orchestrator import run_exported_task_instances
from payskills_runtime.platform.task_instance import run_platform_task_instance


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if argv and argv[0] == "platform-task-instance":
        return run_platform_task_instance(argv[1:])
    if argv and argv[0] == "task-instance-core":
        return run_task_instance_core(argv[1:])
    if argv and argv[0] == "build-task-instance-image":
        return run_build_task_instance_image(argv[1:])
    if argv and argv[0] == "build-runtime-image":
        return run_build_runtime_image(argv[1:])

    parser = argparse.ArgumentParser(prog="payskills-run")
    parser.add_argument("--export-root", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    args, remaining = parser.parse_known_args(argv)

    export_root = Path(args.export_root).resolve()
    config = Path(args.config).resolve() if args.config else export_root / "config" / "config.yaml"
    if remaining:
        print("unhandled args: {0}".format(" ".join(remaining)), file=sys.stderr)
        return 2

    if args.doctor:
        return run_doctor(export_root, config)
    if args.dry_run:
        return run_dry_run(export_root, config)

    return run_exported_task_instances(export_root, config)


if __name__ == "__main__":
    raise SystemExit(main())
