import fnmatch
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from payskills_runtime.export.layout import (
    EXPORT_CONFIG_TEMPLATE_FILES,
    EXPORT_TEMPLATE_FILES,
    RUNTIME_KIT_DIRS,
    RUNTIME_KIT_FILES,
    RUNTIME_SOURCE_EXPORT_DIR,
)
from payskills_runtime.common.manifest_contract import expected_manifest_contract


EXCLUDED_NAMES = {
    ".env",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "logs",
    "runs",
    "node_modules",
}
EXCLUDED_PATTERNS = {
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".DS_Store",
    "llm_config.json",
}


def kit_root() -> Path:
    return Path(__file__).resolve().parents[2]


def should_ignore_export_name(name: str) -> bool:
    if name in EXCLUDED_NAMES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_PATTERNS)


def _ignore(_directory, names):
    return {name for name in names if should_ignore_export_name(name)}


def copy_export_tree(source: Path, target: Path) -> None:
    shutil.copytree(str(source), str(target), ignore=_ignore, copy_function=shutil.copy2)


def copy_runtime_kit(source_kit_root: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for dirname in RUNTIME_KIT_DIRS:
        copy_export_tree(source_kit_root / dirname, target / dirname)
    for filename in RUNTIME_KIT_FILES:
        source = source_kit_root / filename
        if source.exists():
            shutil.copy2(str(source), str(target / filename))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def paths_overlap(first: Path, second: Path) -> bool:
    return first == second or _is_relative_to(first, second) or _is_relative_to(second, first)


def source_symlinks(root: Path):
    for path in sorted(root.rglob("*")):
        if any(should_ignore_export_name(part) for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            yield path.relative_to(root)


def _load_benchmark_suite_metadata(benchmark_suite_root: Path) -> dict:
    metadata_path = benchmark_suite_root / "benchmark_suite.json"
    if not metadata_path.exists():
        return {}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _available_versions(benchmark_suite_root: Path):
    versions_root = benchmark_suite_root / "versions"
    if not versions_root.is_dir():
        return []
    return sorted(path.name for path in versions_root.iterdir() if path.is_dir())


def select_version_dir(benchmark_suite_root: Path, requested_version: str = "") -> Path:
    versions = _available_versions(benchmark_suite_root)
    if not versions:
        raise SystemExit("benchmark_suite has no versions directory: {0}".format(benchmark_suite_root))
    metadata = _load_benchmark_suite_metadata(benchmark_suite_root)
    selected_version = requested_version or str(metadata.get("current_version") or "").strip()
    if not selected_version:
        if len(versions) == 1:
            selected_version = versions[0]
        else:
            raise SystemExit(
                "benchmark_suite version is required; available versions: {0}".format(", ".join(versions))
            )
    version_dir = benchmark_suite_root / "versions" / selected_version
    if not version_dir.is_dir():
        raise SystemExit(
            "benchmark_suite version does not exist: {0}; available versions: {1}".format(
                selected_version,
                ", ".join(versions),
            )
        )
    return version_dir


def selected_source_symlinks(benchmark_suite_root: Path, version_dir: Path):
    metadata_path = benchmark_suite_root / "benchmark_suite.json"
    if metadata_path.is_symlink():
        yield metadata_path.relative_to(benchmark_suite_root)
    for rel_path in source_symlinks(version_dir):
        yield version_dir.relative_to(benchmark_suite_root) / rel_path


def copy_selected_benchmark_suite(benchmark_suite_root: Path, version_dir: Path, target: Path) -> None:
    copy_export_tree(version_dir, target)
    metadata_path = benchmark_suite_root / "benchmark_suite.json"
    if metadata_path.exists():
        shutil.copy2(str(metadata_path), str(target / metadata_path.name))
    version_path = target / "version.json"
    if not version_path.exists():
        version_path.write_text(
            json.dumps({"version": version_dir.name}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def write_manifest(out_dir: Path, name: str, benchmark_suite_root: Path, selected_version: str) -> None:
    manifest = expected_manifest_contract()
    manifest.update(
        {
            "name": name,
            "runtime_source_path": RUNTIME_SOURCE_EXPORT_DIR,
            "benchmark_suite_path": "benchmark_suite",
            "selected_version": selected_version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_benchmark_suite": benchmark_suite_root.name,
        }
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def copy_templates(templates: Path, out_dir: Path) -> None:
    for filename in EXPORT_TEMPLATE_FILES:
        shutil.copy2(str(templates / filename), str(out_dir / filename))
    config_dir = out_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for filename in EXPORT_CONFIG_TEMPLATE_FILES:
        shutil.copy2(str(templates / filename), str(config_dir / filename))
    os.chmod(str(out_dir / "run.sh"), 0o755)


def export_benchmark_suite(benchmark_suite_root: Path, out_dir: Path, name: str, version: str = "") -> None:
    benchmark_suite_root = benchmark_suite_root.resolve()
    out_dir = out_dir.resolve()
    if not benchmark_suite_root.is_dir():
        raise SystemExit("benchmark_suite root does not exist: {0}".format(benchmark_suite_root))
    if paths_overlap(benchmark_suite_root, out_dir):
        raise SystemExit("output directory must not overlap the source benchmark_suite root: {0}".format(out_dir))
    version_dir = select_version_dir(benchmark_suite_root, version)
    symlinks = list(selected_source_symlinks(benchmark_suite_root, version_dir))
    if symlinks:
        raise SystemExit("source benchmark_suite contains symlink: {0}".format(symlinks[0]))
    if out_dir.exists():
        shutil.rmtree(str(out_dir))

    source_kit_root = kit_root()
    out_dir.mkdir(parents=True)
    copy_templates(source_kit_root / "export" / "templates", out_dir)
    copy_selected_benchmark_suite(benchmark_suite_root, version_dir, out_dir / "benchmark_suite")
    copy_runtime_kit(source_kit_root, out_dir / RUNTIME_SOURCE_EXPORT_DIR)
    write_manifest(out_dir, name or benchmark_suite_root.name, benchmark_suite_root, version_dir.name)
