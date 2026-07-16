import shutil
import stat
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Tuple

from payskills_runtime.task_instance import task_instance_dockerfile
from payskills_runtime.config import truthy
from payskills_runtime.docker.commands import (
    docker_run_command,
    docker_run_timeout,
    docker_sandbox_init_command,
    docker_task_instance_core_command,
)
from payskills_runtime.docker.images import (
    DEFAULT_AGENT_RUNTIME_VERSION,
    default_agent_layer_dir,
    docker_image_name,
    ensure_runtime_image,
)
from payskills_runtime.execution import execution_phase_exit, standard_logs_dir


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def docker_daemon_ready() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=10,
        )
    except Exception:
        return False
    return int(proc.returncode) == 0


def make_tree_nonroot_writable(paths: Iterable[Path]) -> None:
    read_write_bits = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH
    execute_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    for path in paths:
        root = Path(path)
        if not root.exists():
            continue
        candidates = [root]
        if root.is_dir():
            candidates.extend(item for item in root.rglob("*") if not item.is_symlink())
        for item in candidates:
            try:
                mode = item.stat().st_mode
                next_mode = mode | read_write_bits
                if item.is_dir() or (mode & execute_bits):
                    next_mode |= execute_bits
                item.chmod(next_mode)
            except OSError:
                continue


def remove_container_from_cidfile(cidfile: Path, log_file) -> None:
    try:
        cid = cidfile.read_text(encoding="utf-8").strip()
    except Exception:
        cid = ""
    if not cid:
        return
    log_file.write("\nremoving docker sandbox container: {0}\n".format(cid))
    subprocess.run(
        ["docker", "rm", "-f", cid],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def container_id_from_cidfile(cidfile: Path) -> str:
    try:
        return cidfile.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def run_task_instance_in_docker(
    task_instance: Dict[str, Path],
    task_instance_dir: Path,
    task_instance_log_dir: Path,
    output_dir: Path,
    workspace_dir: Path,
    kit_dir: Path,
    config: Dict,
    runtime_env: Dict[str, str],
    runtime_input_mounts=None,
) -> Tuple[int, int]:
    docker_cfg = config.get("docker") or {}
    dockerfile = task_instance_dockerfile(task_instance_dir)
    logs_dir = standard_logs_dir(task_instance_log_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if not dockerfile.exists():
        (logs_dir / "docker_build.log").write_text(
            "missing Dockerfile: {0}\n".format(dockerfile),
            encoding="utf-8",
        )
        return 127, 127

    task_instance_image = docker_image_name(task_instance, task_instance_dir, config)
    agent_cfg = config.get("agent") or {}
    agent_runtime_version = str(
        docker_cfg.get("agent_runtime_version") or agent_cfg.get("runtime_version") or DEFAULT_AGENT_RUNTIME_VERSION
    )
    with (logs_dir / "docker_build.log").open("w", encoding="utf-8") as log_file:
        try:
            image = ensure_runtime_image(
                task_instance_dir=task_instance_dir,
                task_instance_id=str(task_instance.get("name") or task_instance_dir.name),
                benchmark_suite=str(config.get("name") or "exported"),
                suite_version=str(task_instance.get("version") or "v0"),
                agent_type=str(agent_cfg.get("type") or agent_cfg.get("provider") or "claude-code"),
                agent_runtime_version=agent_runtime_version,
                agent_layer_dir=default_agent_layer_dir(),
                task_instance_image=task_instance_image,
                build_task_instance=truthy(docker_cfg.get("build", True)),
                log_file=log_file,
            )
        except subprocess.CalledProcessError as exc:
            return int(exc.returncode), 127
        except SystemExit as exc:
            log_file.write("{0}\n".format(exc))
            return 1, 127

    cidfile = output_dir / "container.cid"
    cidfile.unlink(missing_ok=True)
    make_tree_nonroot_writable((workspace_dir, output_dir))

    run_cmd = docker_run_command(
        task_instance_dir,
        output_dir,
        workspace_dir,
        kit_dir,
        image,
        config,
        runtime_env,
        cidfile,
        task_instance=task_instance,
        runtime_input_mounts=runtime_input_mounts,
    )
    with (logs_dir / "docker_stdout.log").open("w", encoding="utf-8") as log_file:
        try:
            proc = subprocess.run(
                run_cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            log_file.write("\ndocker run timed out after 120s\n")
            remove_container_from_cidfile(cidfile, log_file)
            return 124, 127
        if int(proc.returncode) != 0:
            return int(proc.returncode), 127

        container = container_id_from_cidfile(cidfile)
        if not container:
            log_file.write("\ndocker run did not write cidfile: {0}\n".format(cidfile))
            return 1, 127

        try:
            init_proc = subprocess.run(
                docker_sandbox_init_command(container),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=120,
            )
            if int(init_proc.returncode) != 0:
                return int(init_proc.returncode), 127

            core_proc = subprocess.run(
                docker_task_instance_core_command(
                    container,
                    task_instance_dir,
                    config,
                    runtime_env,
                    task_instance=task_instance,
                ),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=docker_run_timeout(config),
            )
            if int(core_proc.returncode) != 0:
                return int(core_proc.returncode), 127
        except subprocess.TimeoutExpired:
            log_file.write("\ndocker task instance timed out after {0}s\n".format(docker_run_timeout(config)))
            return 124, 127
        finally:
            remove_container_from_cidfile(cidfile, log_file)
    return (
        execution_phase_exit(output_dir, "run", 127),
        execution_phase_exit(output_dir, "evaluation", 127),
    )
