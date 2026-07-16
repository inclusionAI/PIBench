import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List


EXPECTED_SCHEMA_VERSION = 1
EXPECTED_EXPORT_LAYOUT = "exported-src-v1"
EXPECTED_RUNNER = "payskills-runtime-kit"
EXPECTED_RUNNER_PATH = "src/bin/payskills-run"
EXPECTED_ENTRYPOINT = "./run.sh"
EXPECTED_COMMANDS = {
    "run": "./run.sh",
    "init": "./run.sh --init",
    "doctor": "./run.sh --doctor",
    "dry_run": "./run.sh --dry-run",
    "help": "./run.sh --help",
}
EXPECTED_TASK_INSTANCE_CONTRACT = {
    "root": "benchmark_suite/task_instances",
    "required_paths": [
        "task_instance.toml",
        "task/Dockerfile",
        "task/run.sh",
        "evaluation/evaluate.sh",
        "evaluation/rubrics.json",
    ],
    "legacy_rejected": ["environment/Dockerfile", "run.sh", "test.sh"],
}
EXPECTED_CONFIG_CONTRACT = {
    "path": "config/config.yaml",
    "example_path": "config/config.example.yaml",
    "env_example_path": "config/.env.example",
    "required_sections": ["run", "agent", "judge", "env", "docker"],
    "secret_fields_are_env_names": ["agent.api_key_env", "judge.api_key_env"],
}
EXPECTED_HELPER_CONTRACT = {
    "bin_dir": "src/bin",
    "helpers": ["payskills-agent", "payskills-judge", "payskills-diff", "payskills-result"],
}
EXPECTED_ARTIFACT_CONTRACT = {
    "run_index": "runs/<timestamp>/summary.json",
    "task_instance_result": "runs/<timestamp>/<task-instance-label>/result.json",
    "task_instance_execution": "runs/<timestamp>/<task-instance-label>/execution.json",
    "logs": "runs/<timestamp>/<task-instance-label>/logs/",
    "artifacts": "runs/<timestamp>/<task-instance-label>/artifacts/",
    "agent_trace": "artifacts/agent_trace.json",
    "agent_evidence": "artifacts/agent_evidence.json",
    "agent_events": "artifacts/agent_events.jsonl",
    "patch": "artifacts/patch.diff",
    "changed_files": "artifacts/changed_files.txt",
    "code_files": "artifacts/code_files/",
}
EXPECTED_MANIFEST_CONTRACT = {
    "schema_version": EXPECTED_SCHEMA_VERSION,
    "layout": EXPECTED_EXPORT_LAYOUT,
    "runner": EXPECTED_RUNNER,
    "runner_path": EXPECTED_RUNNER_PATH,
    "entrypoint": EXPECTED_ENTRYPOINT,
    "commands": EXPECTED_COMMANDS,
    "task_instance_contract": EXPECTED_TASK_INSTANCE_CONTRACT,
    "config_contract": EXPECTED_CONFIG_CONTRACT,
    "helper_contract": EXPECTED_HELPER_CONTRACT,
    "artifact_contract": EXPECTED_ARTIFACT_CONTRACT,
}


def expected_manifest_contract() -> Dict:
    return deepcopy(EXPECTED_MANIFEST_CONTRACT)


def load_manifest(export_root: Path) -> Dict:
    manifest_path = export_root / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _manifest_contract_value_errors(path: str, actual, expected) -> List[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return ["unsupported manifest {0} {1!r}".format(path, actual)]
        errors = []
        for key, expected_value in expected.items():
            child_path = "{0}.{1}".format(path, key) if path else key
            errors.extend(_manifest_contract_value_errors(child_path, actual.get(key), expected_value))
        return errors
    if actual != expected:
        return ["unsupported manifest {0} {1!r}".format(path, actual)]
    return []


def manifest_contract_value_errors(manifest: Dict) -> List[str]:
    return _manifest_contract_value_errors("", manifest, EXPECTED_MANIFEST_CONTRACT)


def manifest_contract_errors(export_root: Path) -> List[str]:
    manifest_path = export_root / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ["package manifest is invalid: manifest.json could not be parsed"]
    if not isinstance(manifest, dict):
        return ["package manifest is invalid: manifest.json must be a JSON object"]
    return manifest_contract_value_errors(manifest)
