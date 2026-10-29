"""Thin wrapper around Nebius Token Factory (OpenAI-compatible API)."""

import json
import os

from openai import OpenAI

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

# Copy exact slugs from the Token Factory model catalog; run
# `python -m secondlook.llm` to list what your key can see.
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            raise RuntimeError("Set NEBIUS_API_KEY (see .env.example)")
        # One retry at most, and chat() sets a per-call timeout, so a stuck call fails fast
        # and the pipeline skips that step instead of hanging the demo.
        _client = OpenAI(base_url=BASE_URL, api_key=key, max_retries=1)
    return _client


def chat(model: str, system: str, user: str, temperature: float = 0.2, timeout: float = 60) -> str:
    resp = client().chat.completions.create(
        model=model,
        temperature=temperature,
        timeout=timeout,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def chat_json(model: str, system: str, user: str, temperature: float = 0.2, timeout: float = 60) -> dict:
    """Ask for a JSON object; tolerate models that wrap it in prose or fences."""
    text = chat(model, system + "\nReply with one JSON object only.", user, temperature, timeout)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON in model reply: {text[:200]}")
    return json.loads(text[start : end + 1])


if __name__ == "__main__":
    for m in client().models.list().data:
        if "emotron" in m.id:
            print(m.id)
    print(chat(NANO, "You are terse.", "Say hello in five words."))
