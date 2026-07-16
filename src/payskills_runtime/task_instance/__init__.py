import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional


_CONTEXT_HASH_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
}
_CONTEXT_HASH_IGNORED_FILES = {".DS_Store"}


def _parse_task_instance_metadata(task_instance_toml: Path) -> Dict[str, str]:
    metadata = {"project": "", "product": "", "scenario": ""}
    try:
        lines = task_instance_toml.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return metadata
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == "[task_instance]"
            continue
        if not in_section or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in metadata:
            metadata[key] = value.strip().strip("\"'")
    return metadata


def task_instance_runtime_env(
    task_instance_dir: Path,
    task_instance: Optional[Mapping[str, object]] = None,
) -> Dict[str, str]:
    """Build the canonical identity and routing environment for task scripts."""
    task_instance_dir = Path(task_instance_dir)
    supplied = dict(task_instance or {})
    metadata = _parse_task_instance_metadata(task_instance_dir / "task_instance.toml")
    task_instance_id = str(supplied.get("name") or task_instance_dir.name)

    def value(field: str) -> str:
        return str(metadata.get(field) or supplied.get(field) or "").strip()

    return {
        "PAYSKILLS_TASK_INSTANCE_ID": task_instance_id,
        "PAYSKILLS_PROJECT": value("project"),
        "PAYSKILLS_PRODUCT": value("product"),
        "PAYSKILLS_SCENARIO": value("scenario"),
        "CASE_NAME": task_instance_id,
        "PAYSKILLS_CASE_NAME": task_instance_id,
    }


def _task_instance_payload(version_dir: Path, task_instance_dir: Path) -> Dict[str, Path]:
    payload = {
        "version": version_dir.name,
        "name": task_instance_dir.name,
        "label": "{0}/{1}".format(version_dir.name, task_instance_dir.name),
        "path": task_instance_dir,
    }
    payload.update(_parse_task_instance_metadata(task_instance_dir / "task_instance.toml"))
    return payload


def _flat_benchmark_suite_version(benchmark_suite_root: Path) -> str:
    version_path = benchmark_suite_root / "version.json"
    if not version_path.exists():
        return ""
    try:
        payload = json.loads(version_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("version") or payload.get("id") or "").strip()


def _flat_task_instance_payload(benchmark_suite_root: Path, task_instance_dir: Path) -> Dict[str, Path]:
    payload = {
        "version": _flat_benchmark_suite_version(benchmark_suite_root),
        "name": task_instance_dir.name,
        "label": task_instance_dir.name,
        "path": task_instance_dir,
    }
    payload.update(_parse_task_instance_metadata(task_instance_dir / "task_instance.toml"))
    return payload


def discover_task_instances(benchmark_suite_root: Path) -> List[Dict[str, Path]]:
    task_instances = []
    flat_task_instances_root = benchmark_suite_root / "task_instances"
    if flat_task_instances_root.is_dir():
        for task_instance_dir in sorted(p for p in flat_task_instances_root.iterdir() if p.is_dir()):
            if (task_instance_dir / "task_instance.toml").exists():
                task_instances.append(_flat_task_instance_payload(benchmark_suite_root, task_instance_dir))
        return task_instances

    versions_root = benchmark_suite_root / "versions"
    if versions_root.is_dir():
        for version_dir in sorted(p for p in versions_root.iterdir() if p.is_dir()):
            task_instances_root = version_dir / "task_instances"
            if not task_instances_root.is_dir():
                continue
            for task_instance_dir in sorted(p for p in task_instances_root.iterdir() if p.is_dir()):
                if (task_instance_dir / "task_instance.toml").exists():
                    task_instances.append(_task_instance_payload(version_dir, task_instance_dir))
        return task_instances

    for task_instance_dir in sorted(p for p in benchmark_suite_root.iterdir() if p.is_dir()):
        if (task_instance_dir / "task_instance.toml").exists():
            payload = {"version": "", "name": task_instance_dir.name, "label": task_instance_dir.name, "path": task_instance_dir}
            payload.update(_parse_task_instance_metadata(task_instance_dir / "task_instance.toml"))
            task_instances.append(payload)
    return task_instances


def filter_task_instances(task_instances: List[Dict[str, Path]], selected: List[str]) -> List[Dict[str, Path]]:
    if not selected:
        return task_instances
    requested = []
    seen = set()
    for item in selected:
        item = item.strip()
        if item and item not in seen:
            requested.append(item)
            seen.add(item)
    matched = []
    labels = {task_instance["label"]: task_instance for task_instance in task_instances}
    names = {}
    for task_instance in task_instances:
        names.setdefault(task_instance["name"], []).append(task_instance)
    ambiguous = []
    missing = []
    for item in requested:
        task_instance = labels.get(item)
        if not task_instance:
            requested_version = ""
            name = item
            if "/" in item:
                requested_version, name = item.rsplit("/", 1)
            name_matches = names.get(name, [])
            if requested_version:
                name_matches = [
                    match for match in name_matches if str(match.get("version") or "") == requested_version
                ]
            if len(name_matches) > 1:
                ambiguous.append(item)
                continue
            if len(name_matches) == 1:
                task_instance = name_matches[0]
        if task_instance and task_instance not in matched:
            matched.append(task_instance)
        elif not task_instance:
            missing.append(item)
    if ambiguous:
        raise SystemExit("configured task instance id is ambiguous: {0}".format(", ".join(ambiguous)))
    if missing:
        raise SystemExit("configured task instance(s) not found: {0}".format(", ".join(missing)))
    return matched


def task_instance_run_script(task_instance_dir: Path) -> Path:
    return task_instance_dir / "task" / "run.sh"


def task_instance_evaluation_script(task_instance_dir: Path) -> Path:
    return task_instance_dir / "evaluation" / "evaluate.sh"


def task_instance_rubrics_file(task_instance_dir: Path) -> Path:
    return task_instance_dir / "evaluation" / "rubrics.json"


def task_instance_dockerfile(task_instance_dir: Path) -> Path:
    return task_instance_dir / "task" / "Dockerfile"


def task_instance_docker_context(task_instance_dir: Path) -> Path:
    return task_instance_dockerfile(task_instance_dir).parent


def task_instance_image_fingerprint(task_instance_dir: Path) -> str:
    context_dir = task_instance_docker_context(task_instance_dir)
    h = hashlib.sha256()
    if not context_dir.exists():
        h.update(str(context_dir).encode("utf-8"))
        return h.hexdigest()[:12]
    paths = sorted(context_dir.rglob("*"), key=lambda path: path.relative_to(context_dir).as_posix())
    for path in paths:
        rel = path.relative_to(context_dir)
        if path.is_dir():
            continue
        if any(part in _CONTEXT_HASH_IGNORED_DIRS for part in rel.parts):
            continue
        if path.name in _CONTEXT_HASH_IGNORED_FILES:
            continue
        h.update(rel.as_posix().encode("utf-8"))
        h.update(b"\0")
        try:
            if path.is_symlink():
                h.update(b"symlink\0")
                h.update(os.readlink(path).encode("utf-8"))
            else:
                h.update(b"file\0")
                h.update(path.read_bytes())
        except OSError:
            h.update(b"unreadable")
        h.update(b"\0")
    return h.hexdigest()[:12]


def safe_docker_image_name(task_instance: Dict[str, Path], task_instance_dir: Path) -> str:
    raw = "payskills-kit-{0}-{1}".format(task_instance["label"], task_instance_image_fingerprint(task_instance_dir))
    return re.sub(r"[^a-z0-9_.-]+", "-", raw.lower()).strip("-")
