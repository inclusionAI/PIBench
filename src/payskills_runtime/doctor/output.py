import sys
from pathlib import Path
from typing import Iterable

from payskills_runtime.doctor.guidance import hints_for_errors


def _stream_or_stdout(stream=None):
    return sys.stdout if stream is None else stream


def print_doctor_header(export_root: Path, config_path: Path, stream=None) -> None:
    stream = _stream_or_stdout(stream)
    print("PaySkills exported benchmark suite doctor", file=stream)
    print("root: {0}".format(export_root), file=stream)
    print("config: {0}".format(config_path), file=stream)


def print_doctor_task_instance_count(task_instance_count: int, stream=None) -> None:
    print("task_instances: {0}".format(task_instance_count), file=_stream_or_stdout(stream))


def print_doctor_config_load_error(error, stream=None) -> None:
    print("ERROR config could not be loaded: {0}".format(error), file=_stream_or_stdout(stream))


def print_doctor_failure(warnings: Iterable[str], errors: Iterable[str], stream=None) -> None:
    stream = _stream_or_stdout(stream)
    error_list = list(errors)
    for warning in warnings:
        print("WARN {0}".format(warning), file=stream)
    for error in error_list:
        print("ERROR {0}".format(error), file=stream)
    for hint in hints_for_errors(error_list):
        print("HINT {0}".format(hint), file=stream)
    print("FAILED", file=stream)


def print_doctor_ok(stream=None) -> None:
    print("OK", file=_stream_or_stdout(stream))
