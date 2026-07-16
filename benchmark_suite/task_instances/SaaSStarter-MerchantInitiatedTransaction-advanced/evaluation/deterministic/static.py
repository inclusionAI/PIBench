#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    mode = sys.argv[3] if len(sys.argv) > 3 else "safety"
    script = Path(__file__).resolve().parent / "support" / "tests" / "run_static.py"
    return subprocess.run([sys.executable, str(script), "--mode", mode, "--project-dir", str(workspace), "--output-dir", str(output_dir)], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
