from pathlib import Path
from typing import Dict, List


DEFAULT_OUTPUT_DIR = "runs"

RESERVED_OUTPUT_DIR_ROOTS = {
    ".git",
    "benchmark_suite",
    "config",
    "kit",
    "src",
}

RESERVED_OUTPUT_DIR_FILES = {
    ".gitignore",
    "README.md",
    "config.example.yaml",
    "config.yaml",
    "manifest.json",
    "run.sh",
}


def output_dir_errors(value) -> List[str]:
    if not isinstance(value, str):
        return ["config run.output_dir must be a string"]

    normalized = value.strip().replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    has_windows_drive = bool(parts and ":" in parts[0])
    if not normalized or normalized.startswith("/") or normalized == "." or has_windows_drive:
        return ["config run.output_dir must be a safe relative path"]
    if any(part in ("", ".", "..") for part in parts):
        return ["config run.output_dir must be a safe relative path"]

    first = parts[0]
    if first in RESERVED_OUTPUT_DIR_ROOTS or first in RESERVED_OUTPUT_DIR_FILES:
        return ["config run.output_dir must not use reserved package path {0}".format(first)]
    return []


def configured_output_dir(config: Dict) -> str:
    run = config.get("run", {}) if isinstance(config, dict) else {}
    if not isinstance(run, dict):
        return DEFAULT_OUTPUT_DIR
    value = run.get("output_dir") or DEFAULT_OUTPUT_DIR
    return str(value)


def resolve_output_root(export_root: Path, config: Dict) -> Path:
    value = configured_output_dir(config)
    errors = output_dir_errors(value)
    if errors:
        raise ValueError(errors[0])
    return Path(export_root) / value


def run_root_for_timestamp(export_root: Path, config: Dict, timestamp: str) -> Path:
    return resolve_output_root(export_root, config) / timestamp
