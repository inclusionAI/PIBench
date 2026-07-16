from typing import Dict


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def config_summary(config: Dict) -> Dict:
    run = config.get("run", {})
    agent = config.get("agent", {})
    judge = config.get("judge", {})
    docker = config.get("docker", {})
    return {
        "parallelism": run.get("parallelism", 1),
        "timeout_sec": run.get("timeout_sec", 3600),
        "task_instances": run.get("task_instances", []),
        "agent": {
            "type": agent.get("type") or agent.get("provider") or "",
            "mode": agent.get("mode", ""),
            "model": agent.get("model", ""),
            "base_url": agent.get("base_url", ""),
            "api_key_env": agent.get("api_key_env", ""),
        },
        "judge": {
            "base_url": judge.get("base_url", ""),
            "api_key_env": judge.get("api_key_env", ""),
            "model": judge.get("model", ""),
        },
        "docker": {
            "enabled": truthy(docker.get("enabled")),
            "build": truthy(docker.get("build", True)),
            "image": str(docker.get("image") or ""),
            "network": str(docker.get("network") or ""),
        },
    }
