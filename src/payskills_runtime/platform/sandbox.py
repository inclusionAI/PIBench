import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

from payskills_runtime.task_instance.invocation import task_instance_core_args
from payskills_runtime.execution import (
    ensure_standard_output_dirs,
    execution_phase_exit,
    load_result,
    standard_artifacts_dir,
    standard_logs_dir,
    standardize_output_layout,
    write_execution_status,
)
from payskills_runtime.execution.runtime_inputs import container_runtime_input_env, prepare_runtime_inputs
from payskills_runtime.docker.images import platform_task_instance_image_name, task_instance_image_fingerprint
from payskills_runtime.platform.task_instance import PlatformTaskInstanceContext


@dataclass(frozen=True)
class PlatformSandboxPaths:
    workspace: str
    output_dir: str
    task_instance_dir: str
    runtime_dir: str
    agent_user: str
    agent_home: str
    claude_config_dir: str
    skills_dir: str
    task_instance_run_sh: str
    task_instance_evaluation_sh: str
    task_instance_instruction_md: str
    task_instance_turns_json: str
    project_fixture_dir: str


@dataclass(frozen=True)
class PlatformSandboxPlan:
    ctx: PlatformTaskInstanceContext
    task_instance_image: str
    sandbox_image: str
    container_name: str
    session_id: str
    paths: PlatformSandboxPaths
    env: Dict[str, str]
    runtime_host_dir: Path
    assets_host_dir: Optional[Path]
    runtime_input_mounts: List[Dict[str, str]]
    runtime_input_cleanup_paths: List[Path]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class PlatformSandboxRun:
    plan: PlatformSandboxPlan
    run_exit_code: Optional[int]
    diff_exit_code: Optional[int]
    evaluation_exit_code: Optional[int]
    agent_runtime_ok: bool


CommandRunner = Callable[..., CommandResult]


def task_instance_image_name(ctx: PlatformTaskInstanceContext) -> str:
    return platform_task_instance_image_name(
        ctx.benchmark_suite,
        ctx.suite_version,
        ctx.task_instance_id,
        task_instance_image_fingerprint(ctx.task_instance_dir),
    )


def container_name(ctx: PlatformTaskInstanceContext, process_id: int) -> str:
    return "payskills_{0}_{1}_{2}".format(ctx.task_instance_id, ctx.mode, process_id)


def session_id(process_id: int, epoch_seconds: int) -> str:
    return "payskills_v2_{0}_{1}".format(epoch_seconds, process_id)


def _runtime_host_dir(ctx: PlatformTaskInstanceContext, env: Mapping[str, str]) -> Path:
    override = str(env.get("PAYSKILLS_RUNTIME_KIT_DIR") or "").strip()
    return Path(override).resolve() if override else ctx.repo_root / "runtime" / "kit"


def _project_fixture_dir(ctx: PlatformTaskInstanceContext, task_instance_dir: str) -> str:
    if (ctx.task_instance_dir / "task" / "fixtures" / "project").is_dir():
        return task_instance_dir + "/task/fixtures/project"
    return task_instance_dir + "/task/fixture/project"


def _paths_for_context(ctx: PlatformTaskInstanceContext, sid: str) -> PlatformSandboxPaths:
    workspace = "/workspace"
    output_dir = "/output"
    task_instance_dir = "/task_instance"
    runtime_dir = "/opt/payskills_runtime"
    agent_user = "agent"
    agent_home = "/home/" + agent_user
    return PlatformSandboxPaths(
        workspace=workspace,
        output_dir=output_dir,
        task_instance_dir=task_instance_dir,
        runtime_dir=runtime_dir,
        agent_user=agent_user,
        agent_home=agent_home,
        claude_config_dir="/tmp/payskills_cc_" + sid,
        skills_dir=task_instance_dir + "/skills",
        task_instance_run_sh=task_instance_dir + "/task/run.sh",
        task_instance_evaluation_sh=task_instance_dir + "/evaluation/evaluate.sh",
        task_instance_instruction_md=task_instance_dir + "/task/instruction.md",
        task_instance_turns_json=task_instance_dir + "/task/turns.json",
        project_fixture_dir=_project_fixture_dir(ctx, task_instance_dir),
    )


def _sandbox_env(
    ctx: PlatformTaskInstanceContext,
    paths: PlatformSandboxPaths,
    env: Mapping[str, str],
) -> Dict[str, str]:
    agent_api_key = env.get("AGENT_API_KEY") or env.get("ANTHROPIC_API_KEY", "")
    agent_base_url = env.get("AGENT_BASE_URL") or env.get("ANTHROPIC_BASE_URL", "")
    rubric_api_key = env.get("RUBRIC_API_KEY", "")
    skill_name = env.get("PAYSKILLS_SKILL_NAME", "")
    if not skill_name and ctx.mode == "with-skill":
        skill_name = infer_skill_name(ctx)
    skill_trigger = env.get("PAYSKILLS_SKILL_TRIGGER", "")
    if not skill_trigger and ctx.mode == "with-skill" and skill_name:
        skill_trigger = "slash"

    values = {
        "AGENT_MODEL": ctx.model,
        "AGENT_API_KEY": agent_api_key,
        "AGENT_BASE_URL": agent_base_url,
        "AGENT_TIMEOUT": str(ctx.agent_timeout),
        "AGENT_MODE": ctx.mode,
        "AGENT_TYPE": ctx.agent_type,
        "WORKDIR": paths.workspace,
        "WORKSPACE": paths.workspace,
        "TASK_INSTANCE_DIR": paths.task_instance_dir,
        "OUTPUT_DIR": paths.output_dir,
        "PAYSKILLS_ARTIFACTS_DIR": paths.output_dir + "/artifacts",
        "PAYSKILLS_LOGS_DIR": paths.output_dir + "/logs",
        "PAYSKILLS_RUNTIME": "v2",
        "PAYSKILLS_RUNTIME_DIR": paths.runtime_dir,
        "PAYSKILLS_SKILLS_DIR": paths.skills_dir,
        "PAYSKILLS_SKILL_TRIGGER": skill_trigger,
        "PAYSKILLS_SKILL_NAME": skill_name,
        "RUBRIC_API_KEY": rubric_api_key,
        "RUBRIC_BASE_URL": env.get("RUBRIC_BASE_URL", ""),
        "RUBRIC_MODEL": env.get("RUBRIC_MODEL", ""),
        "ANTHROPIC_API_KEY": agent_api_key,
        "ANTHROPIC_BASE_URL": agent_base_url,
        "CLAUDE_CONFIG_DIR": paths.claude_config_dir,
        "PATH": paths.runtime_dir + "/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONPATH": paths.runtime_dir,
    }
    for key, value in env.items():
        if key.startswith("BENCHMARK_SUITE_OPT_"):
            values[key] = value
            values[key[len("BENCHMARK_SUITE_OPT_"):]] = value
    return {key: str(value) for key, value in values.items()}


def infer_skill_name(ctx: PlatformTaskInstanceContext) -> str:
    try:
        text = (ctx.task_instance_dir / "task_instance.toml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    match = re.search(r"required\s*=\s*\[([^\]]+)\]", text)
    if match:
        names = re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group(1))
        for left, right in names:
            value = left or right
            if value:
                return value
    skills_dir = ctx.task_instance_dir / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                return child.name
    return ""


def build_sandbox_plan(
    ctx: PlatformTaskInstanceContext,
    *,
    env: Optional[Mapping[str, str]] = None,
    process_id: Optional[int] = None,
    epoch_seconds: Optional[int] = None,
    sandbox_image: str = "",
) -> PlatformSandboxPlan:
    env_map = dict(os.environ if env is None else env)
    pid = int(process_id if process_id is not None else os.getpid())
    epoch = int(epoch_seconds if epoch_seconds is not None else time.time())
    sid = session_id(pid, epoch)
    paths = _paths_for_context(ctx, sid)
    assets = ctx.task_instances_dir / "assets"
    prepared_runtime_inputs = prepare_runtime_inputs(ctx.task_instance_dir, {}, env=env_map)
    sandbox_env = _sandbox_env(ctx, paths, env_map)
    sandbox_env.update(container_runtime_input_env(prepared_runtime_inputs))
    return PlatformSandboxPlan(
        ctx=ctx,
        task_instance_image=task_instance_image_name(ctx),
        sandbox_image=sandbox_image,
        container_name=container_name(ctx, pid),
        session_id=sid,
        paths=paths,
        env=sandbox_env,
        runtime_host_dir=_runtime_host_dir(ctx, env_map),
        assets_host_dir=assets if assets.is_dir() else None,
        runtime_input_mounts=prepared_runtime_inputs.mounts,
        runtime_input_cleanup_paths=prepared_runtime_inputs.cleanup_paths,
    )


def docker_run_command(plan: PlatformSandboxPlan) -> List[str]:
    command = [
        "docker",
        "run",
        "-d",
        "--privileged",
        "--name",
        plan.container_name,
    ]
    for key, value in plan.env.items():
        command.extend(["-e", "{0}={1}".format(key, value)])
    for mount in plan.runtime_input_mounts:
        command.extend(["-v", "{0}:{1}:ro".format(Path(mount["host_path"]).resolve(), mount["container_path"])])
    command.extend([plan.sandbox_image, "sleep", "infinity"])
    return command


def task_instance_copy_command(plan: PlatformSandboxPlan) -> List[str]:
    return [
        "docker",
        "cp",
        str(plan.ctx.task_instance_dir) + "/.",
        plan.container_name + ":" + plan.paths.task_instance_dir + "/",
    ]


def assets_copy_command(plan: PlatformSandboxPlan) -> Optional[List[str]]:
    if not plan.assets_host_dir:
        return None
    return [
        "docker",
        "cp",
        str(plan.assets_host_dir) + "/.",
        plan.container_name + ":" + plan.paths.task_instance_dir + "/_benchmark_suite_assets/",
    ]


def runtime_copy_command(plan: PlatformSandboxPlan) -> List[str]:
    return [
        "docker",
        "cp",
        str(plan.runtime_host_dir) + "/.",
        plan.container_name + ":" + plan.paths.runtime_dir + "/",
    ]


def build_runtime_image_command(ctx: PlatformTaskInstanceContext) -> List[str]:
    return [
        str(ctx.repo_root / "runtime" / "kit" / "bin" / "payskills-run"),
        "build-runtime-image",
        "--task-instance-dir",
        str(ctx.task_instance_dir),
        "--task-instance-id",
        ctx.task_instance_id,
        "--benchmark-suite",
        ctx.benchmark_suite,
        "--suite-version",
        ctx.suite_version,
        "--agent-type",
        ctx.agent_type,
    ]


def init_sandbox_command(plan: PlatformSandboxPlan) -> List[str]:
    paths = plan.paths
    script = """
set -e
if ! id {agent_user} >/dev/null 2>&1; then
    useradd -m -s /bin/bash {agent_user}
fi
if command -v sudo >/dev/null 2>&1; then
    echo '{agent_user} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/payskills-agent 2>/dev/null || true
    chmod 0440 /etc/sudoers.d/payskills-agent 2>/dev/null || true
fi
mkdir -p '{task_instance_dir}' '{workspace}' '{output_dir}' '{output_dir}/logs' '{output_dir}/artifacts' '{runtime_dir}' '{claude_config_dir}' '{agent_home}'
chmod 777 '{workspace}' '{output_dir}' '{claude_config_dir}'
chown -R '{agent_user}:{agent_user}' '{workspace}' '{output_dir}' '{claude_config_dir}' '{agent_home}' 2>/dev/null || true
mkdir -p /etc/profile.d
cat > /etc/profile.d/payskills-runtime-v2.sh <<'EOF'
export PATH=/opt/payskills_runtime/bin:/opt/venv/bin:$PATH
export PYTHONPATH=/opt/payskills_runtime:${{PYTHONPATH:-}}
export TASK_INSTANCE_DIR=/task_instance
export OUTPUT_DIR=/output
export PAYSKILLS_ARTIFACTS_DIR=/output/artifacts
export PAYSKILLS_LOGS_DIR=/output/logs
export WORKDIR=/workspace
export WORKSPACE=/workspace
EOF
chmod +x /etc/profile.d/payskills-runtime-v2.sh
""".format(
        agent_user=paths.agent_user,
        task_instance_dir=paths.task_instance_dir,
        workspace=paths.workspace,
        output_dir=paths.output_dir,
        runtime_dir=paths.runtime_dir,
        claude_config_dir=paths.claude_config_dir,
        agent_home=paths.agent_home,
    )
    return ["docker", "exec", plan.container_name, "bash", "-c", script]


def docker_auth_setup_commands(plan: PlatformSandboxPlan, docker_config_file: Optional[Path]) -> List[List[str]]:
    if not docker_config_file or not docker_config_file.exists() or docker_config_file.stat().st_size <= 0:
        return []
    paths = plan.paths
    install_script = """
set -e
install -m 0600 /tmp/payskills_docker_config.json /root/.docker/config.json
if install -m 0600 -o '{agent_user}' -g '{agent_user}' /tmp/payskills_docker_config.json '{agent_home}/.docker/config.json' 2>/dev/null; then
    :
else
    cp /tmp/payskills_docker_config.json '{agent_home}/.docker/config.json'
    chmod 0600 '{agent_home}/.docker/config.json'
    chown '{agent_user}:{agent_user}' '{agent_home}/.docker/config.json' 2>/dev/null || true
fi
rm -f /tmp/payskills_docker_config.json
""".format(agent_user=paths.agent_user, agent_home=paths.agent_home)
    return [
        ["docker", "exec", plan.container_name, "bash", "-c", "mkdir -p /root/.docker '{0}/.docker'".format(paths.agent_home)],
        ["docker", "cp", str(docker_config_file), plan.container_name + ":/tmp/payskills_docker_config.json"],
        ["docker", "exec", plan.container_name, "bash", "-c", install_script],
    ]


def dind_setup_command(plan: PlatformSandboxPlan) -> List[str]:
    script = """
if command -v dockerd >/dev/null 2>&1; then
    groupadd -f docker
    usermod -aG docker '{agent_user}' || true
    dockerd --storage-driver=vfs > /tmp/dockerd.log 2>&1 &
    for i in $(seq 1 30); do
        docker info >/dev/null 2>&1 && break
        sleep 1
    done
fi
""".format(agent_user=plan.paths.agent_user)
    return ["docker", "exec", plan.container_name, "bash", "-c", script]


def post_copy_permissions_command(plan: PlatformSandboxPlan) -> List[str]:
    paths = plan.paths
    script = """
chmod +x '{runtime_dir}'/bin/* 2>/dev/null || true
chmod +x '{task_instance_run_sh}' '{task_instance_evaluation_sh}' 2>/dev/null || true
chown -R '{agent_user}:{agent_user}' '{task_instance_dir}' '{output_dir}' '{workspace}' '{agent_home}' '{claude_config_dir}' 2>/dev/null || true
""".format(
        runtime_dir=paths.runtime_dir,
        task_instance_run_sh=paths.task_instance_run_sh,
        task_instance_evaluation_sh=paths.task_instance_evaluation_sh,
        agent_user=paths.agent_user,
        task_instance_dir=paths.task_instance_dir,
        output_dir=paths.output_dir,
        workspace=paths.workspace,
        agent_home=paths.agent_home,
        claude_config_dir=paths.claude_config_dir,
    )
    return ["docker", "exec", plan.container_name, "bash", "-c", script]


def _exec_env_args(env_values: Mapping[str, str]) -> List[str]:
    args: List[str] = []
    for key, value in env_values.items():
        args.extend(["-e", "{0}={1}".format(key, value)])
    return args


def _agent_exec_command(
    plan: PlatformSandboxPlan,
    *,
    env_values: Mapping[str, str],
    command: List[str],
    workdir: Optional[str] = None,
    user: Optional[str] = None,
) -> List[str]:
    result = ["docker", "exec"]
    if workdir:
        result.extend(["-w", workdir])
    if user:
        result.extend(["-u", user])
    result.extend(_exec_env_args(env_values))
    result.append(plan.container_name)
    result.extend(command)
    return result


def _runtime_env(plan: PlatformSandboxPlan) -> Dict[str, str]:
    return {
        "HOME": plan.paths.agent_home,
        "PATH": plan.paths.runtime_dir + "/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONPATH": plan.paths.runtime_dir,
        "PAYSKILLS_ARTIFACTS_DIR": plan.paths.output_dir + "/artifacts",
        "PAYSKILLS_LOGS_DIR": plan.paths.output_dir + "/logs",
    }


def _agent_runtime_env(plan: PlatformSandboxPlan) -> Dict[str, str]:
    values = _runtime_env(plan)
    values["CLAUDE_CONFIG_DIR"] = plan.paths.claude_config_dir
    return values


def agent_doctor_command(plan: PlatformSandboxPlan) -> List[str]:
    return _agent_exec_command(
        plan,
        workdir=plan.paths.workspace,
        user=plan.paths.agent_user,
        env_values=_runtime_env(plan),
        command=[
            "payskills-agent",
            "doctor",
            "--output",
            plan.paths.output_dir + "/artifacts/agent_runtime_doctor.json",
        ],
    )


def prepare_workspace_command(plan: PlatformSandboxPlan) -> List[str]:
    runtime_input_lines = []
    for mount in plan.runtime_input_mounts:
        workspace_path = str(mount.get("workspace_path") or "").strip()
        if not workspace_path:
            continue
        target = plan.paths.workspace + "/" + workspace_path
        runtime_input_lines.append(
            "mkdir -p {parent} && cp {source} {target}".format(
                parent=shlex.quote(str(Path(target).parent)),
                source=shlex.quote(str(mount["container_path"])),
                target=shlex.quote(target),
            )
        )
    runtime_input_script = "\n".join(runtime_input_lines)
    script = """
set -e
if [[ -d '{project_fixture_dir}' ]]; then
    cp -a '{project_fixture_dir}/.' '{workspace}/'
fi
{runtime_input_script}
chown -R '{agent_user}:{agent_user}' '{workspace}' 2>/dev/null || true
""".format(
        project_fixture_dir=plan.paths.project_fixture_dir,
        workspace=plan.paths.workspace,
        runtime_input_script=runtime_input_script,
        agent_user=plan.paths.agent_user,
    )
    return ["docker", "exec", plan.container_name, "bash", "-c", script]


def prepare_skills_command(plan: PlatformSandboxPlan) -> List[str]:
    env_values = _agent_runtime_env(plan)
    env_values.update({"AGENT_MODE": plan.ctx.mode, "AGENT_TYPE": plan.ctx.agent_type})
    return _agent_exec_command(
        plan,
        workdir=plan.paths.workspace,
        user=plan.paths.agent_user,
        env_values=env_values,
        command=[
            "payskills-agent",
            "prepare-skills",
            "--agent-type",
            plan.ctx.agent_type,
            "--mode",
            plan.ctx.mode,
            "--skills",
            plan.paths.skills_dir,
            "--workspace",
            plan.paths.workspace,
            "--home",
            plan.paths.agent_home,
        ],
    )


def _relative_task_instance_script(plan: PlatformSandboxPlan, script_path: str) -> str:
    try:
        return Path(script_path).relative_to(Path(plan.paths.task_instance_dir)).as_posix()
    except ValueError:
        return script_path


def task_instance_label(ctx: PlatformTaskInstanceContext) -> str:
    return "{0}/{1}".format(ctx.suite_version, ctx.task_instance_id) if ctx.suite_version else ctx.task_instance_id


def task_instance_core_command(plan: PlatformSandboxPlan) -> List[str]:
    env_values = dict(plan.env)
    env_values.update(_agent_runtime_env(plan))
    return _agent_exec_command(
        plan,
        workdir=plan.paths.workspace,
        user=plan.paths.agent_user,
        env_values=env_values,
        command=task_instance_core_args(
            task_instance_dir=plan.paths.task_instance_dir,
            workspace=plan.paths.workspace,
            output_dir=plan.paths.output_dir,
            kit_dir=plan.paths.runtime_dir,
            run_script=_relative_task_instance_script(plan, plan.paths.task_instance_run_sh),
            evaluation_script=_relative_task_instance_script(plan, plan.paths.task_instance_evaluation_sh),
            timeout_sec=plan.ctx.agent_timeout,
            task_instance_id=plan.ctx.task_instance_id,
            suite_version=plan.ctx.suite_version,
            task_instance_label=task_instance_label(plan.ctx),
        ),
    )


def copy_output_command(plan: PlatformSandboxPlan, log_dir: Path) -> List[str]:
    return [
        "docker",
        "cp",
        plan.container_name + ":" + plan.paths.output_dir + "/.",
        str(log_dir) + "/",
    ]


def cleanup_container_command(plan: PlatformSandboxPlan) -> List[str]:
    return ["docker", "rm", "-f", plan.container_name]


def default_command_runner(
    command: List[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    output_path: Optional[Path] = None,
    stderr_to_stdout: bool = False,
) -> CommandResult:
    stdout_target = subprocess.PIPE if capture_output else None
    stderr_target = subprocess.PIPE if capture_output else None
    output_handle = None
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        output_handle = Path(output_path).open("w", encoding="utf-8")
        stdout_target = output_handle
        stderr_target = subprocess.STDOUT if stderr_to_stdout else None
        capture_output = False
    try:
        proc = subprocess.run(
            command,
            stdout=stdout_target,
            stderr=stderr_target,
            universal_newlines=True,
        )
    finally:
        if output_handle is not None:
            output_handle.close()
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, command, output=proc.stdout, stderr=proc.stderr)
    return CommandResult(returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


def _docker_auth_config_file(env: Mapping[str, str]) -> Optional[Path]:
    explicit = str(env.get("PAYSKILLS_DOCKER_CONFIG_FILE") or "").strip()
    if explicit:
        return Path(explicit)
    config_dir = str(env.get("DOCKER_CONFIG") or "").strip()
    if not config_dir:
        home = str(env.get("HOME") or "").strip()
        config_dir = str(Path(home) / ".docker") if home else ""
    return Path(config_dir) / "config.json" if config_dir else None


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def collect_task_instance_snapshots(ctx: PlatformTaskInstanceContext, log_dir: Path) -> None:
    log_path = Path(log_dir)
    snapshot_dir = standard_artifacts_dir(log_path) / "task_instance_snapshot"
    _copy_if_exists(ctx.task_instance_dir / "task" / "instruction.md", snapshot_dir / "instruction.md")
    _copy_if_exists(ctx.task_instance_dir / "task_instance.toml", snapshot_dir / "task_instance.toml")
    _copy_if_exists(ctx.task_instance_dir / "task" / "turns.json", snapshot_dir / "turns.json")
    _copy_if_exists(ctx.task_instance_dir / "task" / "run.sh", snapshot_dir / "run.sh.snapshot")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "evaluate.sh", snapshot_dir / "evaluate.sh.snapshot")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "deterministic" / "static.py", snapshot_dir / "deterministic" / "static.py")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "deterministic" / "integration.py", snapshot_dir / "deterministic" / "integration.py")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "deterministic" / "e2e.py", snapshot_dir / "deterministic" / "e2e.py")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "rubrics.json", snapshot_dir / "rubrics.json")
    _copy_if_exists(ctx.task_instance_dir / "evaluation" / "deterministic" / "rubrics.json", snapshot_dir / "rubrics.json")


def run_sandbox_task_instance(
    ctx: PlatformTaskInstanceContext,
    log_dir: Path,
    *,
    runner=default_command_runner,
    env: Optional[Mapping[str, str]] = None,
    process_id: Optional[int] = None,
    epoch_seconds: Optional[int] = None,
) -> PlatformSandboxRun:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    ensure_standard_output_dirs(log_path)
    logs_dir = standard_logs_dir(log_path)
    plan = bootstrap_sandbox(
        ctx,
        runner=runner,
        env=env,
        process_id=process_id,
        epoch_seconds=epoch_seconds,
    )
    try:
        doctor = runner(
            agent_doctor_command(plan),
            check=False,
            output_path=logs_dir / "agent_runtime_doctor.log",
            stderr_to_stdout=True,
        )
        if doctor.returncode != 0:
            runner(copy_output_command(plan, log_path), check=False)
            standardize_output_layout(log_path)
            collect_task_instance_snapshots(ctx, log_path)
            write_execution_status(
                log_path,
                task_instance={"name": ctx.task_instance_id, "version": ctx.suite_version, "label": ctx.task_instance_id},
                result=load_result(log_path),
                run_exit=None,
                diff_exit=None,
                evaluation_exit=None,
                metadata={"agent_runtime_ok": False},
            )
            return PlatformSandboxRun(
                plan=plan,
                run_exit_code=None,
                diff_exit_code=None,
                evaluation_exit_code=None,
                agent_runtime_ok=False,
            )

        runner(prepare_workspace_command(plan))
        runner(
            prepare_skills_command(plan),
            check=False,
            output_path=logs_dir / "prepare_skills.log",
            stderr_to_stdout=True,
        )
        core_result = runner(
            task_instance_core_command(plan),
            check=False,
            output_path=logs_dir / "task_instance_core.log",
            stderr_to_stdout=True,
        )
        runner(copy_output_command(plan, log_path), check=False)
        standardize_output_layout(log_path)
        collect_task_instance_snapshots(ctx, log_path)
        run_exit = execution_phase_exit(log_path, "run", core_result.returncode)
        diff_exit = execution_phase_exit(log_path, "diff", 127)
        evaluation_exit = execution_phase_exit(log_path, "evaluation", 127)
        write_execution_status(
            log_path,
            task_instance={"name": ctx.task_instance_id, "version": ctx.suite_version, "label": ctx.task_instance_id},
            result=load_result(log_path),
            run_exit=run_exit,
            diff_exit=diff_exit,
            evaluation_exit=evaluation_exit,
            metadata={"agent_runtime_ok": True},
        )
        return PlatformSandboxRun(
            plan=plan,
            run_exit_code=run_exit,
            diff_exit_code=diff_exit,
            evaluation_exit_code=evaluation_exit,
            agent_runtime_ok=True,
        )
    finally:
        runner(cleanup_container_command(plan), check=False)
        for path in plan.runtime_input_cleanup_paths:
            shutil.rmtree(path, ignore_errors=True)


def bootstrap_sandbox(
    ctx: PlatformTaskInstanceContext,
    *,
    runner=default_command_runner,
    env: Optional[Mapping[str, str]] = None,
    process_id: Optional[int] = None,
    epoch_seconds: Optional[int] = None,
) -> PlatformSandboxPlan:
    env_map = dict(os.environ if env is None else env)
    image_result = runner(build_runtime_image_command(ctx), capture_output=True)
    sandbox_image = image_result.stdout.strip()
    plan = build_sandbox_plan(
        ctx,
        env=env_map,
        process_id=process_id,
        epoch_seconds=epoch_seconds,
        sandbox_image=sandbox_image,
    )

    started = False
    try:
        runner(docker_run_command(plan))
        started = True
        runner(init_sandbox_command(plan))

        for command in docker_auth_setup_commands(plan, _docker_auth_config_file(env_map)):
            runner(command)

        runner(dind_setup_command(plan))
        runner(task_instance_copy_command(plan))
        assets_command = assets_copy_command(plan)
        if assets_command:
            runner(assets_command)
        runner(runtime_copy_command(plan))
        runner(post_copy_permissions_command(plan))
    except Exception:
        if started:
            runner(cleanup_container_command(plan), check=False)
        for path in plan.runtime_input_cleanup_paths:
            shutil.rmtree(path, ignore_errors=True)
        raise
    return plan
