import os
import shutil
from pathlib import Path
from typing import List, Optional, Union


def copy_skills(skills_dir: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    if not skills_dir.exists():
        return
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        destination = target_root / child.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(child, destination)


def prepare_skills(
    agent_type: str,
    mode: str,
    skills_dir: Union[str, Path],
    workspace: Union[str, Path],
    home: Union[str, Path],
    *,
    openclaw_profile: str = "",
    claude_config_dir: Optional[Union[str, Path]] = None,
) -> List[Path]:
    """Install case skills into the real skill directory for each agent."""
    if mode != "with-skill":
        return []
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        return []

    workspace_path = Path(workspace)
    home_path = Path(home)
    if agent_type == "claude-code":
        config_dir = Path(claude_config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or home_path / ".claude")
        targets = [config_dir / "skills"]
    elif agent_type == "openclaw":
        state_dir = f".openclaw-{openclaw_profile}" if openclaw_profile else ".openclaw"
        targets = [home_path / state_dir / "skills"]
    elif agent_type == "hermes":
        targets = [home_path / ".hermes" / "skills"]
    else:
        raise ValueError(f"unsupported agent type: {agent_type}")

    for target in targets:
        copy_skills(skills_path, target)
    return targets
