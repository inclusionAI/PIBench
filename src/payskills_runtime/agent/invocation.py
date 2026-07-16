import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from payskills_runtime.agent.providers import (
    build_claude_command,
    build_hermes_command,
    build_openclaw_command,
    configure_claude_env,
    configure_hermes,
    configure_openclaw,
    openai_base_url,
)


def build_agent_environment(agent_type: str, home: Path, workspace: Path, model: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["AGENT_MODEL"] = model
    if "AGENT_API_KEY" not in env and "ANTHROPIC_API_KEY" in env:
        env["AGENT_API_KEY"] = env["ANTHROPIC_API_KEY"]
    if "AGENT_BASE_URL" not in env and "ANTHROPIC_BASE_URL" in env:
        env["AGENT_BASE_URL"] = env["ANTHROPIC_BASE_URL"]

    if agent_type == "openclaw":
        configure_openclaw(home, workspace, env)
    if agent_type == "hermes":
        configure_hermes(home, env)
        env["OPENAI_API_KEY"] = env.get("AGENT_API_KEY", "")
        env["OPENAI_BASE_URL"] = openai_base_url(env.get("AGENT_BASE_URL", ""))
    if agent_type == "claude-code":
        configure_claude_env(env)
    return env


def prepare_agent_turn(agent_type: str, *, turn_index: int, workspace: Path, env: Dict[str, str]) -> None:
    if agent_type != "openclaw" or turn_index != 1:
        return
    subprocess.run(
        ["openclaw", "exec-policy", "preset", "yolo"],
        cwd=str(workspace),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["openclaw", "agents", "add", "coder", "--workspace", str(workspace), "--non-interactive"],
        cwd=str(workspace),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def build_agent_turn_command(
    agent_type: str,
    *,
    model: str,
    max_turns: int,
    session_id: str,
    resume_session_id: str,
    turn_index: int,
    turn_message: str,
    effective_input: str,
    include_system_instruction: bool,
    system_instruction: str,
    openclaw_session_arg: str,
    timeout: int,
) -> List[str]:
    if agent_type == "claude-code":
        return build_claude_command(
            model=model,
            max_turns=max_turns,
            session_id=session_id,
            resume_session_id=resume_session_id,
            turn_index=turn_index,
            turn_message=turn_message,
            system_instruction=system_instruction,
        )
    if agent_type == "openclaw":
        return build_openclaw_command(
            message=effective_input if include_system_instruction else turn_message,
            session_id=openclaw_session_arg,
            timeout=timeout,
        )
    if agent_type == "hermes":
        return build_hermes_command(
            message=effective_input if include_system_instruction else turn_message,
            model=model,
            max_turns=max_turns,
            resume_session_id=resume_session_id,
            turn_index=turn_index,
        )
    raise ValueError("unsupported agent type: {0}".format(agent_type))


def agent_command_timeout(agent_type: str, timeout: int) -> int:
    if agent_type == "openclaw":
        return timeout + 10
    return timeout


def run_command(
    cmd: List[str],
    *,
    cwd: Path,
    env: Dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    input_text: Optional[str] = None,
    timeout: Optional[int] = None,
) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_f, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr_f:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env,
                input=input_text,
                universal_newlines=True,
                stdout=stdout_f,
                stderr=stderr_f,
                timeout=timeout,
                check=False,
            )
            return int(proc.returncode)
        except subprocess.TimeoutExpired:
            stderr_f.write("timeout after {0}s\n".format(timeout))
            return 124
