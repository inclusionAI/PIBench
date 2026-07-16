#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    mode = sys.argv[3] if len(sys.argv) > 3 else "basic"
    task_instance_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(__file__).resolve().parents[2]
    support_dir = task_instance_dir / "evaluation" / "deterministic" / "support"
    script = support_dir / "tests" / "run_integration.py"
    return subprocess.run([sys.executable, str(script), "--mode", mode, "--case-dir", str(support_dir), "--project-dir", str(workspace), "--output-dir", str(output_dir)], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
