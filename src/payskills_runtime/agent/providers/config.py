import json
import uuid
from pathlib import Path
from typing import Dict


def openai_base_url(agent_base_url: str) -> str:
    if "api.anthropic.com" in agent_base_url:
        return "https://api.anthropic.com/v1"
    if "zenmux.ai" in agent_base_url:
        return "https://zenmux.ai/api/v1"
    if "openrouter.ai" in agent_base_url:
        return "https://openrouter.ai/api/v1"
    return agent_base_url


def configure_claude_env(env: Dict[str, str]) -> str:
    config_dir = f"/tmp/payskills_cc_{uuid.uuid4().hex[:10]}"
    env["CLAUDE_CONFIG_DIR"] = config_dir
    return config_dir


def configure_openclaw(home: Path, workspace: Path, env: Dict[str, str]) -> None:
    model = env.get("AGENT_MODEL", "")
    base_url = env.get("AGENT_BASE_URL") or env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
    api_kind = "anthropic-messages" if model.lower().startswith("claude") else "openai-completions"
    oc_url = base_url if api_kind == "anthropic-messages" else openai_base_url(base_url)
    config_dir = home / ".openclaw"
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "models": {
            "providers": {
                "payskills": {
                    "baseUrl": oc_url,
                    "apiKey": env.get("AGENT_API_KEY") or env.get("ANTHROPIC_API_KEY") or "",
                    "api": api_kind,
                    "models": [
                        {
                            "id": model,
                            "name": model,
                            "input": ["text"],
                            "contextWindow": 200000,
                            "maxTokens": 16384,
                        }
                    ],
                }
            }
        },
        "agents": {"defaults": {"workspace": str(workspace)}},
        "tools": {"exec": {"host": "gateway", "security": "full", "ask": "off"}},
    }
    (config_dir / "openclaw.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def configure_hermes(home: Path, env: Dict[str, str]) -> None:
    config_dir = home / ".hermes"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_url = env.get("AGENT_BASE_URL") or env.get("ANTHROPIC_BASE_URL") or ""
    openai_url = openai_base_url(base_url)
    api_key = env.get("AGENT_API_KEY") or env.get("ANTHROPIC_API_KEY") or ""
    model = env.get("AGENT_MODEL", "")
    config = (
        "model:\n"
        f"  default: \"{model}\"\n"
        "  provider: \"custom\"\n"
        f"  base_url: \"{openai_url}\"\n"
        f"  api_key: \"{api_key}\"\n"
        "tools:\n"
        "  terminal:\n"
        "    backend: \"local\"\n"
        "    enabled: true\n"
        "  web:\n"
        "    enabled: false\n"
    )
    (config_dir / "config.yaml").write_text(config, encoding="utf-8")
