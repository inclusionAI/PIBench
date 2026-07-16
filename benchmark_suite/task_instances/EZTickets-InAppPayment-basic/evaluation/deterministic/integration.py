#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output/checks/integration.json")
    output_dir = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    support = Path(__file__).resolve().parent / "support"
    out.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "SUPPORT_DIR": str(support),
            "TASK_INSTANCE_DIR": str(Path(__file__).resolve().parents[2]),
            "WORKSPACE": str(workspace),
            "OUTPUT_DIR": str(output_dir),
        }
    )
    proc = subprocess.run(["bash", str(support / "integration_test.sh")], env=env, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
