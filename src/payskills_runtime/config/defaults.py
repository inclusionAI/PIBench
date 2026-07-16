from pathlib import Path
from typing import Dict

from payskills_runtime.config.format import load_config_source


DEFAULT_CONFIG = {
    "run": {
        "parallelism": 1,
        "output_dir": "runs",
        "timeout_sec": 3600,
        "task_instances": [],
    },
    "agent": {
        "type": "claude-code",
        "mode": "no-skill",
        "model": "",
        "base_url": "",
        "api_key_env": "",
    },
    "judge": {
        "base_url": "",
        "api_key_env": "",
        "model": "",
    },
    "env": {},
    "runtime_inputs": {},
    "docker": {
        "enabled": False,
        "build": True,
        "network": "",
    },
}


def deep_merge(base: Dict, override: Dict) -> Dict:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Path) -> Dict:
    config_path = Path(config_path)
    loaded = load_config_source(config_path)
    config = deep_merge(DEFAULT_CONFIG, loaded)
    config["__config_path"] = str(config_path)
    config["__config_dir"] = str(config_path.parent)
    run = config.setdefault("run", {})
    try:
        run["parallelism"] = max(1, int(run.get("parallelism") or 1))
    except (TypeError, ValueError):
        run["parallelism"] = 1
    try:
        run["timeout_sec"] = max(1, int(run.get("timeout_sec") or 3600))
    except (TypeError, ValueError):
        run["timeout_sec"] = 3600
    task_instances = run.get("task_instances") or []
    if isinstance(task_instances, str):
        task_instances = [task_instances]
    run["task_instances"] = [str(task_instance) for task_instance in task_instances if str(task_instance).strip()]
    config.setdefault("agent", {})
    if "provider" in config["agent"] and not config["agent"].get("type"):
        config["agent"]["type"] = config["agent"]["provider"]
    config.setdefault("judge", {})
    config.setdefault("env", {})
    if not isinstance(config["env"], dict):
        config["env"] = {}
    config.setdefault("docker", {})
    return config
