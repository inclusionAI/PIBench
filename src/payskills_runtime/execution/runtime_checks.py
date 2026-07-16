import os
from typing import Dict, List, Set

from payskills_runtime.config import truthy
from payskills_runtime.docker.host import command_exists, docker_daemon_ready


SUPPORTED_AGENT_TYPES = {"claude-code", "openclaw", "hermes"}
SUPPORTED_AGENT_MODES = {"no-skill", "with-skill"}
REQUIRED_HOST_COMMANDS = ("bash", "python3", "git")
AGENT_COMMANDS = {
    "claude-code": "claude",
    "openclaw": "openclaw",
    "hermes": "hermes",
}


def validate_host_commands(errors: List[str]) -> None:
    for command in REQUIRED_HOST_COMMANDS:
        if not command_exists(command):
            errors.append("missing command {0}".format(command))


def validate_agent_config(config: Dict, errors: List[str], *, required: bool = False) -> None:
    agent_cfg = config.get("agent") or {}
    agent_type = str(agent_cfg.get("type") or agent_cfg.get("provider") or "").strip()
    agent_mode = str(agent_cfg.get("mode") or "").strip()
    agent_base_url = str(agent_cfg.get("base_url") or "").strip()
    agent_model = str(agent_cfg.get("model") or "").strip()
    agent_api_key_env = str(agent_cfg.get("api_key_env") or "").strip()
    if agent_type and agent_type not in SUPPORTED_AGENT_TYPES:
        errors.append("unsupported agent.type {0}".format(agent_type))
    if agent_mode and agent_mode not in SUPPORTED_AGENT_MODES:
        errors.append("unsupported agent.mode {0}".format(agent_mode))
    if required and not agent_model:
        errors.append("agent.model is required because selected task instances call payskills-agent")
    if agent_base_url or agent_api_key_env:
        if not agent_base_url:
            errors.append("agent.base_url is required when agent provider config is set")
        if not agent_model and not required:
            errors.append("agent.model is required when agent.base_url is set")
        if not agent_api_key_env:
            errors.append("agent.api_key_env is required when agent.base_url is set")
    if agent_api_key_env and not os.environ.get(agent_api_key_env):
        errors.append("missing env {0}".format(agent_api_key_env))


def validate_judge_config(config: Dict, errors: List[str], *, required: bool = False) -> None:
    judge_cfg = config.get("judge") or {}
    judge_base_url = str(judge_cfg.get("base_url") or "").strip()
    judge_model = str(judge_cfg.get("model") or "").strip()
    api_key_env = str(judge_cfg.get("api_key_env") or "").strip()
    if required:
        if not judge_base_url:
            errors.append("judge.base_url is required because selected task instances call payskills-judge")
        if not judge_model:
            errors.append("judge.model is required because selected task instances call payskills-judge")
        if not api_key_env:
            errors.append("judge.api_key_env is required because selected task instances call payskills-judge")
    elif judge_base_url or judge_model or api_key_env:
        if not judge_base_url:
            errors.append("judge.base_url is required when judge config is set")
        if not judge_model:
            errors.append("judge.model is required when judge.base_url is set")
        if not api_key_env:
            errors.append("judge.api_key_env is required when judge.base_url is set")
    if api_key_env and not os.environ.get(api_key_env):
        errors.append("missing env {0}".format(api_key_env))


def validate_agent_command(config: Dict, errors: List[str], *, required: bool = False) -> None:
    if not required or truthy((config.get("docker") or {}).get("enabled")):
        return
    agent_cfg = config.get("agent") or {}
    agent_type = str(agent_cfg.get("type") or agent_cfg.get("provider") or "claude-code").strip()
    command = AGENT_COMMANDS.get(agent_type)
    if command and not command_exists(command):
        errors.append("missing command {0} for agent.type {1}".format(command, agent_type))


def validate_docker_config(config: Dict, errors: List[str]) -> None:
    docker_cfg = config.get("docker") or {}
    if truthy(docker_cfg.get("enabled")):
        if not command_exists("docker"):
            errors.append("missing command docker")
        elif not docker_daemon_ready():
            errors.append("docker daemon is not reachable")
        if not truthy(docker_cfg.get("build", True)) and not str(docker_cfg.get("image") or "").strip():
            errors.append("docker.image is required when docker.build is false")


def validate_runtime_requirements(
    config: Dict,
    requirements: Set[str],
    errors: List[str],
    *,
    check_host_commands: bool = True,
) -> None:
    if check_host_commands:
        validate_host_commands(errors)
    validate_agent_config(config, errors, required="agent" in requirements)
    validate_agent_command(config, errors, required="agent" in requirements)
    validate_judge_config(config, errors, required="judge" in requirements)
    validate_docker_config(config, errors)
