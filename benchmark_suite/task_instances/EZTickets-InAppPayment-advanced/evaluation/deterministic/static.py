#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output/checks/static.json")
    support = Path(__file__).resolve().parent / "support"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["python3", str(support / "static_checks.py"), str(workspace), str(out)],
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
