import json
import re
from typing import Any, Dict

try:
    from urllib.request import Request, urlopen
except ImportError:  # pragma: no cover - Python 2 fallback is harmless.
    from urllib2 import Request, urlopen


def messages_url(base_url: str) -> str:
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    if base.endswith("/v1/messages") or base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return base + "/messages"
    return base + "/v1/messages"


def openai_chat_completions_url(base_url: str) -> str:
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if "zenmux.ai" in base:
        return "https://zenmux.ai/api/v1/chat/completions"
    if "openrouter.ai" in base:
        return "https://openrouter.ai/api/v1/chat/completions"
    if "api.minimaxi.com" in base:
        return "https://api.minimaxi.com/v1/chat/completions"
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def strip_visible_thinking(text: str) -> str:
    return re.sub(r"<think\b[^>]*>.*?</think>\s*", "", text or "", flags=re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> str:
    text = strip_visible_thinking(text).strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in judge response")

    depth = 0
    in_string = False
    escape_next = False
    for index in range(start, len(text)):
        char = text[index]
        if escape_next:
            escape_next = False
            continue
        if char == "\\" and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("Unclosed JSON object in judge response")


def response_text(payload: Dict[str, Any]) -> str:
    if payload.get("text"):
        return str(payload.get("text"))
    texts = []
    thinking = []
    content = payload.get("content", [])
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
            elif block.get("type") == "thinking":
                thinking.append(str(block.get("thinking") or ""))
    if texts:
        return "".join(texts)
    if thinking:
        return "".join(thinking)
    for key in ("text", "result", "message"):
        if payload.get(key):
            return str(payload.get(key))
    return json.dumps(payload, ensure_ascii=False)


def uses_max_completion_tokens(model: str) -> bool:
    model_name = (model or "").lower().split("/")[-1]
    return model_name.startswith("gpt-5")


def stream_data_lines(response: Any):
    while True:
        line = response.readline()
        if not line:
            break
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        yield data


def parse_openai_stream(response: Any) -> Dict[str, Any]:
    texts = []
    usage = None
    finish_reason = None
    event_count = 0
    reasoning_chars = 0

    for data in stream_data_lines(response):
        event_count += 1
        payload = json.loads(data)
        if payload.get("usage"):
            usage = payload.get("usage")
        choices = payload.get("choices") or []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if content:
                texts.append(str(content))
            for key in ("reasoning_content", "reasoning"):
                if delta.get(key):
                    reasoning_chars += len(str(delta.get(key)))

    text = "".join(texts)
    return {
        "text": text,
        "content": [{"type": "text", "text": text}],
        "usage": usage,
        "metadata": {
            "api_style": "openai-chat-completions",
            "stream": True,
            "event_count": event_count,
            "finish_reason": finish_reason,
            "reasoning_chars": reasoning_chars,
        },
    }


def call_judge(
    prompt: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    token_key = "max_completion_tokens" if uses_max_completion_tokens(model) else "max_tokens"
    payload[token_key] = max_tokens
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        openai_chat_completions_url(base_url),
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "content-type": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return parse_openai_stream(resp)
