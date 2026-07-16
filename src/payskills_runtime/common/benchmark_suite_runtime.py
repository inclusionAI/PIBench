from pathlib import Path
from typing import Union


def parse_benchmark_suite_runtime_version(path: Union[str, Path]) -> str:
    """Return the runtime version declared in a version-level benchmark_suite.toml."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "v2"

    in_benchmark_suite = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[benchmark_suite]":
            in_benchmark_suite = True
            continue
        if line.startswith("["):
            in_benchmark_suite = False
            continue
        if not in_benchmark_suite or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "runtime_version":
            version = value.strip().strip('"').strip("'").strip()
            return version or "v2"
    return "v2"
