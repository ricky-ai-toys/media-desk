"""DeepSeek (deepseek-v4-flash) OpenAI-compatible client used for all analysis."""
import json
import os

import httpx

from . import config

SYSTEM_EDITOR = (
    "You are the senior desk analyst for International Financial Media Weekly. "
    "Work only from provided source material. Never invent quotes, names, or facts. "
    "When a claim is not supported, say so explicitly. Output is machine-parsed: "
    "follow field formats exactly."
)


def _headers():
    key = os.environ.get(config.ANALYSIS["api_key_env"])
    if not key:
        raise RuntimeError(f"Missing {config.ANALYSIS['api_key_env']} env var")
    return {"Authorization": f"Bearer {key}"}


def chat(messages: list[dict], json_mode: bool = False, max_tokens: int = 8192,
         temperature: float | None = None) -> str:
    """Non-streaming completion with optional JSON response."""
    payload = {
        "model": config.ANALYSIS["model"],
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        payload["temperature"] = temperature
    else:
        payload["temperature"] = config.ANALYSIS["temperature"]
    with httpx.Client(timeout=600) as client:
        r = client.post(
            f"{config.ANALYSIS['base_url']}/chat/completions", headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        return content


def chat_json(system: str, user: str, max_tokens: int = 8192) -> dict:
    """JSON-mode completion; returns parsed object with a raw copy attached."""
    out = chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], json_mode=True, max_tokens=max_tokens)
    try:
        return json.loads(_strip_fences(out))
    except json.JSONDecodeError:
        raise ValueError(f"LLM returned non-JSON: {out[:400]}")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0]
    return t.strip()