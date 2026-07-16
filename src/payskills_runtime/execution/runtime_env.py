import os
from typing import Dict


def runtime_env_from_config(config: Dict) -> Dict[str, str]:
    agent = config.get("agent", {})
    judge = config.get("judge", {})
    env = {}
    agent_type = agent.get("type") or agent.get("provider")
    if agent_type:
        env["AGENT_TYPE"] = str(agent_type)
    if agent.get("model"):
        env["AGENT_MODEL"] = str(agent.get("model"))
    if agent.get("mode"):
        env["AGENT_MODE"] = str(agent.get("mode"))
    if agent.get("base_url"):
        env["AGENT_BASE_URL"] = str(agent.get("base_url"))
        if str(agent_type) == "claude-code":
            env["ANTHROPIC_BASE_URL"] = str(agent.get("base_url"))
    agent_api_key_env = agent.get("api_key_env")
    if agent_api_key_env and os.environ.get(str(agent_api_key_env)):
        env["AGENT_API_KEY"] = os.environ[str(agent_api_key_env)]
        if str(agent_type) == "claude-code":
            env["ANTHROPIC_API_KEY"] = os.environ[str(agent_api_key_env)]
    if judge.get("base_url"):
        env["RUBRIC_BASE_URL"] = str(judge.get("base_url"))
    if judge.get("model"):
        env["RUBRIC_MODEL"] = str(judge.get("model"))
    api_key_env = judge.get("api_key_env")
    if api_key_env and os.environ.get(str(api_key_env)):
        env["RUBRIC_API_KEY"] = os.environ[str(api_key_env)]
    for key, value in (config.get("env") or {}).items():
        env[str(key)] = "" if value is None else str(value)
    return env
