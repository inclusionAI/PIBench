from typing import List


def build_claude_command(
    *,
    model: str,
    max_turns: int,
    session_id: str,
    resume_session_id: str,
    turn_index: int,
    turn_message: str,
    system_instruction: str,
) -> List[str]:
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        str(max_turns),
    ]
    if turn_index == 1:
        if system_instruction:
            cmd.extend(["--system-prompt", system_instruction])
        cmd.extend(["--session-id", session_id])
    else:
        cmd.extend(["--resume", resume_session_id or session_id])
    cmd.extend(["--", turn_message])
    return cmd


def build_openclaw_command(*, message: str, session_id: str, timeout: int) -> List[str]:
    return [
        "openclaw",
        "agent",
        "--agent",
        "coder",
        "--local",
        "--message",
        message,
        "--json",
        "--session-id",
        session_id,
        "--timeout",
        str(timeout),
    ]


def build_hermes_command(
    *,
    message: str,
    model: str,
    max_turns: int,
    resume_session_id: str,
    turn_index: int,
) -> List[str]:
    cmd = [
        "hermes",
        "chat",
        "--query",
        message,
        "--quiet",
        "--model",
        model,
        "--provider",
        "custom",
        "--max-turns",
        str(max_turns),
        "--yolo",
    ]
    if turn_index > 1 and resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    return cmd
