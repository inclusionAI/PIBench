#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    support = Path(__file__).resolve().parent / "support"
    return subprocess.run(["python3", str(support / "integration_tests.py"), str(workspace), str(output_dir)], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
