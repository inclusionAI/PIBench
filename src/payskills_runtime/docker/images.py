import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, TextIO

from payskills_runtime.task_instance import (
    task_instance_docker_context,
    task_instance_dockerfile,
    task_instance_run_script,
    task_instance_evaluation_script,
    safe_docker_image_name,
    task_instance_image_fingerprint,
)


DEFAULT_AGENT_RUNTIME_VERSION = "2026-06-26-agent-runtime-v1"


def safe_image_name(raw: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", raw.lower()).strip("-")


def platform_task_instance_image_name(
    benchmark_suite: str,
    suite_version: str,
    task_instance_id: str,
    fingerprint: str = "",
) -> str:
    suffix = "-{0}".format(fingerprint[:12]) if fingerprint else ""
    return safe_image_name(
        "payskills-{0}-{1}-{2}{3}".format(
            benchmark_suite or "default",
            suite_version or "v0",
            task_instance_id,
            suffix,
        )
    )


def runtime_image_name(
    *,
    benchmark_suite: str,
    suite_version: str,
    task_instance_id: str,
    agent_type: str,
    agent_runtime_version: str,
    task_instance_image_id: str,
) -> str:
    short_id = task_instance_image_id.strip()
    if short_id.startswith("sha256:"):
        short_id = short_id[len("sha256:") :]
    short_id = short_id[:12] or "unknown"
    raw = "payskills-runtime-v2-{0}-{1}-{2}-{3}-{4}-{5}".format(
        benchmark_suite or "default",
        suite_version or "v0",
        task_instance_id,
        agent_type or "claude-code",
        agent_runtime_version or DEFAULT_AGENT_RUNTIME_VERSION,
        short_id,
    )
    return safe_image_name(raw)[:180]


def docker_image_name(task_instance: Dict[str, Path], task_instance_dir: Path, config: Dict) -> str:
    docker_cfg = config.get("docker") or {}
    return str(docker_cfg.get("image") or safe_docker_image_name(task_instance, task_instance_dir))


def docker_build_command(task_instance_dir: Path, image: str, dockerfile: Optional[Path] = None, docker_bin: str = "docker") -> List[str]:
    return [
        docker_bin,
        "build",
        "-t",
        image,
        "-f",
        str(dockerfile or task_instance_dockerfile(task_instance_dir)),
        str(task_instance_docker_context(task_instance_dir)),
    ]


def validate_task_instance_layout(task_instance_dir: Path) -> List[str]:
    errors: List[str] = []
    if not task_instance_dir.is_dir():
        return ["Task instance 不存在: {0}".format(task_instance_dir)]
    required = (
        task_instance_dir / "task_instance.toml",
        task_instance_dir / "task",
        task_instance_dir / "evaluation",
        task_instance_dir / "task" / "instruction.md",
        task_instance_dockerfile(task_instance_dir),
        task_instance_run_script(task_instance_dir),
        task_instance_evaluation_script(task_instance_dir),
    )
    for path in required:
        if not path.exists():
            errors.append("缺少 {0}: {1}".format(path.relative_to(task_instance_dir), task_instance_dir))
    legacy = (
        (task_instance_dir / "run.sh", "旧格式 root run.sh 已不支持，请迁移到 task/run.sh"),
        (task_instance_dir / "test.sh", "旧格式 root test.sh 已不支持，请迁移到 evaluation/evaluate.sh"),
        (task_instance_dir / "environment" / "Dockerfile", "旧格式 environment/Dockerfile 已不支持，请迁移到 task/Dockerfile"),
    )
    for path, message in legacy:
        if path.exists():
            errors.append("{0}: {1}".format(message, task_instance_dir))
    return errors


def _run_docker(command: List[str], log_file: Optional[TextIO] = None, *, check: bool = True) -> subprocess.CompletedProcess:
    stdout = log_file if log_file is not None else None
    stderr = subprocess.STDOUT if log_file is not None else None
    proc = subprocess.run(command, stdout=stdout, stderr=stderr, universal_newlines=True)
    if check and int(proc.returncode) != 0:
        raise subprocess.CalledProcessError(proc.returncode, command)
    return proc


def _docker_output(command: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if check and int(proc.returncode) != 0:
        raise subprocess.CalledProcessError(proc.returncode, command, output=proc.stdout, stderr=proc.stderr)
    return proc


def inspect_image_id(image: str, *, docker_bin: str = "docker") -> Optional[str]:
    proc = _docker_output([docker_bin, "image", "inspect", "-f", "{{.Id}}", image], check=False)
    if int(proc.returncode) != 0:
        return None
    return proc.stdout.strip()


def image_exists(image: str, *, docker_bin: str = "docker") -> bool:
    proc = _docker_output([docker_bin, "image", "inspect", image], check=False)
    return int(proc.returncode) == 0


def build_task_instance_image(
    task_instance_dir: Path,
    image: str,
    *,
    docker_bin: str = "docker",
    no_cache: bool = False,
    log_file: Optional[TextIO] = None,
) -> None:
    errors = validate_task_instance_layout(task_instance_dir)
    if errors:
        raise SystemExit("\n".join("ERROR: {0}".format(error) for error in errors))

    command = docker_build_command(task_instance_dir, image, docker_bin=docker_bin)
    if no_cache:
        command.insert(2, "--no-cache")
    _run_docker(command, log_file=log_file)


def build_runtime_image(
    *,
    task_instance_image: str,
    runtime_image: str,
    agent_type: str,
    agent_runtime_version: str,
    agent_layer_dir: Path,
    docker_bin: str = "docker",
    log_file: Optional[TextIO] = None,
) -> None:
    if not (agent_layer_dir / "install_agents.sh").exists():
        raise SystemExit("missing agent layer script: {0}".format(agent_layer_dir / "install_agents.sh"))
    if not (agent_layer_dir / "doctor.sh").exists():
        raise SystemExit("missing agent layer script: {0}".format(agent_layer_dir / "doctor.sh"))

    build_dir = Path(tempfile.mkdtemp(prefix="payskills-runtime-v2."))
    try:
        shutil.copy2(agent_layer_dir / "install_agents.sh", build_dir / "install_agents.sh")
        shutil.copy2(agent_layer_dir / "doctor.sh", build_dir / "doctor.sh")
        (build_dir / "Dockerfile").write_text(
            """ARG CASE_IMAGE
FROM ${CASE_IMAGE}

ARG PAYSKILLS_AGENT_TYPE
ARG PAYSKILLS_V2_AGENT_RUNTIME_VERSION
LABEL org.payskills.runtime="v2"
LABEL org.payskills.agent_type="${PAYSKILLS_AGENT_TYPE}"
LABEL org.payskills.agent_runtime_version="${PAYSKILLS_V2_AGENT_RUNTIME_VERSION}"
ENV PAYSKILLS_AGENT_TYPE="${PAYSKILLS_AGENT_TYPE}"

COPY install_agents.sh /opt/payskills-agent-layer/install_agents.sh
COPY doctor.sh /opt/payskills-agent-layer/doctor.sh

RUN sh /opt/payskills-agent-layer/install_agents.sh
RUN sh /opt/payskills-agent-layer/doctor.sh --build-check
""",
            encoding="utf-8",
        )
        _run_docker(
            [
                docker_bin,
                "build",
                "-t",
                runtime_image,
                "--build-arg",
                "CASE_IMAGE={0}".format(task_instance_image),
                "--build-arg",
                "PAYSKILLS_AGENT_TYPE={0}".format(agent_type or "claude-code"),
                "--build-arg",
                "PAYSKILLS_V2_AGENT_RUNTIME_VERSION={0}".format(agent_runtime_version),
                str(build_dir),
            ],
            log_file=log_file,
        )
    finally:
        shutil.rmtree(str(build_dir), ignore_errors=True)


def ensure_runtime_image(
    *,
    task_instance_dir: Path,
    task_instance_id: str,
    benchmark_suite: str,
    suite_version: str,
    agent_type: str,
    agent_runtime_version: str,
    agent_layer_dir: Path,
    docker_bin: str = "docker",
    task_instance_image: Optional[str] = None,
    build_task_instance: bool = True,
    log_file: Optional[TextIO] = None,
) -> str:
    if not task_instance_image:
        task_instance_image = platform_task_instance_image_name(
            benchmark_suite,
            suite_version,
            task_instance_id,
            task_instance_image_fingerprint(task_instance_dir),
        )
    if not image_exists(task_instance_image, docker_bin=docker_bin):
        if not build_task_instance:
            raise SystemExit("task instance image does not exist and docker.build is false: {0}".format(task_instance_image))
        build_task_instance_image(task_instance_dir, task_instance_image, docker_bin=docker_bin, log_file=log_file)
    task_instance_image_id = inspect_image_id(task_instance_image, docker_bin=docker_bin)
    if not task_instance_image_id:
        raise SystemExit("failed to inspect task instance image id: {0}".format(task_instance_image))

    runtime_image = runtime_image_name(
        benchmark_suite=benchmark_suite,
        suite_version=suite_version,
        task_instance_id=task_instance_id,
        agent_type=agent_type,
        agent_runtime_version=agent_runtime_version,
        task_instance_image_id=task_instance_image_id,
    )
    if image_exists(runtime_image, docker_bin=docker_bin):
        return runtime_image
    build_runtime_image(
        task_instance_image=task_instance_image,
        runtime_image=runtime_image,
        agent_type=agent_type,
        agent_runtime_version=agent_runtime_version,
        agent_layer_dir=agent_layer_dir,
        docker_bin=docker_bin,
        log_file=log_file,
    )
    return runtime_image


def default_agent_layer_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docker" / "agent-layer"


def run_build_task_instance_image(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="payskills-run build-task-instance-image")
    parser.add_argument("--task-instance-dir", required=True)
    parser.add_argument("--task-instance-id", required=True)
    parser.add_argument("--benchmark-suite", default=os.environ.get("PAYSKILLS_BENCHMARK_SUITE", "default"))
    parser.add_argument("--suite-version", default=os.environ.get("PAYSKILLS_SUITE_VERSION", "v0"))
    parser.add_argument("--docker-bin", default=os.environ.get("PAYSKILLS_DOCKER_BIN", "docker"))
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    task_instance_dir = Path(args.task_instance_dir)
    image = platform_task_instance_image_name(
        args.benchmark_suite,
        args.suite_version,
        args.task_instance_id,
        task_instance_image_fingerprint(task_instance_dir),
    )
    build_task_instance_image(task_instance_dir, image, docker_bin=args.docker_bin, no_cache=args.no_cache)
    print(image)
    return 0


def run_build_runtime_image(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="payskills-run build-runtime-image")
    parser.add_argument("--task-instance-dir", required=True)
    parser.add_argument("--task-instance-id", required=True)
    parser.add_argument("--benchmark-suite", default=os.environ.get("PAYSKILLS_BENCHMARK_SUITE", "default"))
    parser.add_argument("--suite-version", default=os.environ.get("PAYSKILLS_SUITE_VERSION", "v0"))
    parser.add_argument(
        "--agent-runtime-version",
        default=os.environ.get("PAYSKILLS_V2_AGENT_RUNTIME_VERSION", DEFAULT_AGENT_RUNTIME_VERSION),
    )
    parser.add_argument(
        "--agent-layer-dir",
        default=os.environ.get("PAYSKILLS_AGENT_LAYER_DIR", str(default_agent_layer_dir())),
    )
    parser.add_argument("--docker-bin", default=os.environ.get("PAYSKILLS_DOCKER_BIN", "docker"))
    parser.add_argument("--task-instance-image", default="")
    parser.add_argument("--agent-type", default=os.environ.get("PAYSKILLS_AGENT_TYPE", "claude-code"))
    parser.add_argument("--no-build-task-instance", action="store_true")
    args = parser.parse_args(argv)

    image = ensure_runtime_image(
        task_instance_dir=Path(args.task_instance_dir),
        task_instance_id=args.task_instance_id,
        benchmark_suite=args.benchmark_suite,
        suite_version=args.suite_version,
        agent_type=args.agent_type,
        agent_runtime_version=args.agent_runtime_version,
        agent_layer_dir=Path(args.agent_layer_dir),
        docker_bin=args.docker_bin,
        task_instance_image=args.task_instance_image or None,
        build_task_instance=not args.no_build_task_instance,
    )
    print(image)
    return 0
