"""
Thin provider-agnostic LLM call used by the judge and the fixer.

Independence knob: VALIDATOR_PROVIDER / VALIDATOR_MODEL / VALIDATOR_API_KEY
override the generator's LLM_* settings, so the reviewer can be a different
model (or a different vendor) from the one that wrote the artefact. When they
are unset the validator falls back to the generator's configuration — still an
independent *pass* (different prompt, different role), just not a different
model.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx


class ValidatorUnavailable(RuntimeError):
    """Raised when no LLM is configured for validation."""


def resolve_config() -> tuple[str, str, str]:
    provider = (os.getenv("VALIDATOR_PROVIDER") or os.getenv("LLM_PROVIDER") or "none").lower()
    model = os.getenv("VALIDATOR_MODEL") or os.getenv("LLM_MODEL") or ""
    api_key = os.getenv("VALIDATOR_API_KEY") or os.getenv("LLM_API_KEY") or ""
    if provider in ("", "none"):
        raise ValidatorUnavailable("No LLM configured (set VALIDATOR_PROVIDER or LLM_PROVIDER).")
    if provider != "ollama" and not api_key:
        raise ValidatorUnavailable("LLM API key missing (VALIDATOR_API_KEY or LLM_API_KEY).")
    if not model:
        model = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o-mini", "gemini": "gemini-1.5-pro", "ollama": "llama3"}.get(provider, "")
    return provider, model, api_key


def is_independent_model() -> bool:
    """True when the validator is pinned to a different model than the generator."""
    v = os.getenv("VALIDATOR_MODEL")
    g = os.getenv("LLM_MODEL")
    return bool(v) and v != g


async def call_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    timeout: float = 120.0,
) -> tuple[str, str, str]:
    """Return (text, provider, model)."""
    provider, model, api_key = resolve_config()

    if provider == "anthropic":
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return text.strip(), provider, model

    if provider == "openai":
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
        return text.strip(), provider, model

    if provider == "ollama":
        base = os.getenv("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/api/generate",
                json={"model": model, "prompt": (system + "\n\n" if system else "") + prompt, "stream": False,
                      "options": {"temperature": temperature}},
            )
            resp.raise_for_status()
            text = resp.json().get("response", "")
        return text.strip(), provider, model

    # Gemini
    import google.generativeai as genai  # type: ignore
    genai.configure(api_key=api_key)
    gm = genai.GenerativeModel(model, system_instruction=system) if system else genai.GenerativeModel(model)
    response = await gm.generate_content_async(prompt, generation_config={"temperature": temperature, "max_output_tokens": max_tokens})
    return (response.text or "").strip(), provider, model


def strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def extract_json(text: str) -> dict:
    """Parse the first JSON object in an LLM reply, tolerating prose/fences."""
    t = strip_fences(text)
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM reply")
    candidate = t[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        # Common failure: trailing commas.
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        return json.loads(candidate)


def numbered(code: str) -> str:
    return "\n".join(f"{i:4d} | {line}" for i, line in enumerate(code.splitlines(), start=1))
