import shutil
import subprocess
from pathlib import Path
from typing import List, Union


def _git(workspace: Path, args: List[str]):
    return subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def init_workspace_git(workspace: Union[str, Path]) -> None:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    _git(workspace, ["init"])
    _git(workspace, ["config", "user.email", "agent@payskills.local"])
    _git(workspace, ["config", "user.name", "Agent"])
    _git(workspace, ["config", "--add", "safe.directory", str(workspace)])
    _git(workspace, ["add", "-A"])
    _git(workspace, ["commit", "-m", "initial", "--allow-empty"])
    info_exclude = workspace / ".git" / "info" / "exclude"
    info_exclude.parent.mkdir(parents=True, exist_ok=True)
    with info_exclude.open("a", encoding="utf-8") as exclude:
        exclude.write("\n.payskills_init_sha\n")
    rev = _git(workspace, ["rev-parse", "HEAD"]).stdout.strip()
    if rev:
        (workspace / ".payskills_init_sha").write_text(rev + "\n", encoding="utf-8")


def export_workspace_diff(workspace: Union[str, Path], output_dir: Union[str, Path]) -> None:
    workspace = Path(workspace)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (workspace / ".git").exists():
        _git(workspace, ["add", "-N", "."])
        patch = _git(workspace, ["diff", "--binary", "HEAD"]).stdout
        changed = _git(workspace, ["diff", "--name-only", "HEAD"]).stdout
    else:
        patch = ""
        changed = ""
    (output_dir / "patch.diff").write_text(patch, encoding="utf-8")
    (output_dir / "changed_files.txt").write_text(changed, encoding="utf-8")

    snapshot = output_dir / "code_files"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir(parents=True, exist_ok=True)
    for rel in [line.strip() for line in changed.splitlines() if line.strip()]:
        src = workspace / rel
        if src.exists() and src.is_file():
            dst = snapshot / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
