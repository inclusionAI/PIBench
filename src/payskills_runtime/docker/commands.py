from pathlib import Path
from typing import Dict, List

from payskills_runtime.task_instance import task_instance_run_script, task_instance_evaluation_script
from payskills_runtime.task_instance.invocation import (
    CONTAINER_TASK_INSTANCE_DIR,
    CONTAINER_KIT_DIR,
    CONTAINER_OUTPUT_DIR,
    CONTAINER_WORKSPACE_DIR,
    task_instance_core_args,
    container_env_args,
)
from payskills_runtime.config import truthy


CONTAINER_AGENT_USER = "agent"
CONTAINER_HOME = "/tmp/payskills-home"
CONTAINER_RUN_USER = CONTAINER_AGENT_USER


def docker_enabled(config: Dict) -> bool:
    return truthy((config.get("docker") or {}).get("enabled"))


def docker_run_command(
    task_instance_dir: Path,
    output_dir: Path,
    workspace_dir: Path,
    kit_dir: Path,
    image: str,
    config: Dict,
    runtime_env: Dict[str, str],
    cidfile: Path,
    task_instance: Dict[str, Path] = None,
    runtime_input_mounts: List[Dict[str, str]] = None,
) -> List[str]:
    docker_cfg = config.get("docker") or {}
    command = [
        "docker",
        "run",
        "-d",
        "--privileged",
        "--cidfile",
        str(cidfile),
        "-v",
        "{0}:/task_instance:ro".format(task_instance_dir.resolve()),
        "-v",
        "{0}:/workspace".format(workspace_dir.resolve()),
        "-v",
        "{0}:/output".format(output_dir.resolve()),
        "-v",
        "{0}:/opt/payskills_runtime:ro".format(kit_dir.resolve()),
        "-w",
        "/workspace",
    ]
    for mount in runtime_input_mounts or []:
        command.extend(
            [
                "-v",
                "{0}:{1}:ro".format(Path(mount["host_path"]).resolve(), mount["container_path"]),
            ]
        )
    network = str(docker_cfg.get("network") or "").strip()
    if network:
        command.extend(["--network", network])
    command.extend([image, "sleep", "infinity"])
    return command


def docker_sandbox_init_command(container: str) -> List[str]:
    script = """
set -e
agent_user="{agent_user}"
if ! id "$agent_user" >/dev/null 2>&1; then
    if command -v useradd >/dev/null 2>&1; then
        useradd -m -s /bin/bash "$agent_user"
    elif command -v adduser >/dev/null 2>&1; then
        adduser --disabled-password --gecos "" "$agent_user" >/dev/null 2>&1 || adduser -D "$agent_user"
    fi
fi
if command -v sudo >/dev/null 2>&1 && id "$agent_user" >/dev/null 2>&1; then
    mkdir -p /etc/sudoers.d
    echo "$agent_user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/payskills-agent
    chmod 0440 /etc/sudoers.d/payskills-agent
fi
mkdir -p "{home}" "{workspace}" "{output}" "{output}/logs" "{output}/artifacts"
chmod 777 "{home}" "{workspace}" "{output}" /tmp 2>/dev/null || true
if id "$agent_user" >/dev/null 2>&1; then
    chown -R "$agent_user:$agent_user" "{home}" "{workspace}" "{output}" 2>/dev/null || true
fi
if command -v dockerd >/dev/null 2>&1; then
    groupadd -f docker 2>/dev/null || true
    usermod -aG docker "$agent_user" 2>/dev/null || true
    if ! docker info >/dev/null 2>&1; then
        dockerd --storage-driver=vfs > /tmp/dockerd.log 2>&1 &
        for i in $(seq 1 30); do
            docker info >/dev/null 2>&1 && break
            sleep 1
        done
    fi
fi
""".format(
        agent_user=CONTAINER_AGENT_USER,
        home=CONTAINER_HOME,
        workspace=CONTAINER_WORKSPACE_DIR,
        output=CONTAINER_OUTPUT_DIR,
    )
    return ["docker", "exec", container, "bash", "-c", script]


def docker_task_instance_core_command(
    container: str,
    task_instance_dir: Path,
    config: Dict,
    runtime_env: Dict[str, str],
    task_instance: Dict[str, Path] = None,
) -> List[str]:
    run_rel = task_instance_run_script(task_instance_dir).relative_to(task_instance_dir).as_posix()
    evaluation_rel = task_instance_evaluation_script(task_instance_dir).relative_to(task_instance_dir).as_posix()
    timeout_sec = int(config.get("run", {}).get("timeout_sec") or 3600)
    task_instance_meta = task_instance or {}
    task_instance_id = str(task_instance_meta.get("name") or task_instance_dir.name)
    suite_version = str(task_instance_meta.get("version") or "")
    task_instance_label = str(task_instance_meta.get("label") or task_instance_id)
    command = ["docker", "exec", "-w", CONTAINER_WORKSPACE_DIR, "-u", CONTAINER_AGENT_USER]
    command.extend(container_env_args(runtime_env))
    command.extend(["-e", "HOME={0}".format(CONTAINER_HOME)])
    command.append(container)
    command.extend(
        task_instance_core_args(
            task_instance_dir=CONTAINER_TASK_INSTANCE_DIR,
            workspace=CONTAINER_WORKSPACE_DIR,
            output_dir=CONTAINER_OUTPUT_DIR,
            kit_dir=CONTAINER_KIT_DIR,
            run_script=run_rel,
            evaluation_script=evaluation_rel,
            timeout_sec=timeout_sec,
            task_instance_id=task_instance_id,
            suite_version=suite_version,
            task_instance_label=task_instance_label,
        )
    )
    return command


def docker_run_timeout(config: Dict) -> int:
    timeout_sec = int(config.get("run", {}).get("timeout_sec") or 3600)
    return max(1, timeout_sec) * 2 + 300
