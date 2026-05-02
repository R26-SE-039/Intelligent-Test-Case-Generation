"""
Gherkin Generator — Jinja2-first with LLM plugin slot.

Architecture:
  GherkinGenerator
    ├── _detect_template()     — keyword matching → template selection
    ├── generate_with_jinja2() — fast, offline, deterministic
    └── generate_with_llm()    — pluggable: OpenAI / CodeLlama / Ollama
                                  (set LLM_PROVIDER env var to enable)

To add a new LLM provider:
  1. Implement BaseLLMProvider in app/gherkin/llm_providers/
  2. Register it in LLM_PROVIDERS dict below
  3. Set LLM_PROVIDER=your_provider in .env
"""

from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ─── Template directory ────────────────────────────────────────────────────────
TEMPLATES_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    trim_blocks=True,
    lstrip_blocks=True,
)

# ─── Keyword → template mapping ───────────────────────────────────────────────
TEMPLATE_KEYWORDS: dict[str, list[str]] = {
    "login.feature.j2": [
        "log in", "login", "sign in", "signin", "authenticate",
        "credentials", "password", "username", "session",
    ],
    "cart.feature.j2": [
        "cart", "add to cart", "remove from cart", "basket",
        "shopping cart", "add item", "remove item",
    ],
    "checkout.feature.j2": [
        "checkout", "purchase", "order", "payment", "pay",
        "shipping", "confirm order", "place order", "buy",
    ],
    "search.feature.j2": [
        "search", "find", "filter", "sort", "browse", "look for",
    ],
}


def _detect_template(story: dict) -> str:
    """
    Detect the best Jinja2 template based on action/goal keywords.
    Falls back to generic.feature.j2 if no match found.
    """
    text = f"{story.get('action', '')} {story.get('goal', '')}".lower()

    for template_name, keywords in TEMPLATE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return template_name

    return "generic.feature.j2"


def _build_feature_name(story: dict) -> str:
    """Convert action text to a proper Feature name."""
    action = story.get("action", "unknown action").title()
    # Capitalise first letter of each word, clean up
    return re.sub(r"\s+", " ", action).strip()


def _parse_acceptance_criteria(raw: str | list) -> list[str]:
    """Safely parse acceptance criteria from either a JSON string or a list."""
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [raw] if raw else []


# ─── Jinja2 generator ─────────────────────────────────────────────────────────

def generate_with_jinja2(story: dict) -> str:
    """
    Generate a Gherkin feature file using Jinja2 templates.
    This is the default, fast, offline generator.
    """
    template_name = _detect_template(story)
    template = jinja_env.get_template(template_name)

    context = {
        "feature_name": _build_feature_name(story),
        "actor": story.get("actor", "user"),
        "action": story.get("action", "perform an action"),
        "goal": story.get("goal", "achieve a result"),
        "acceptance_criteria": _parse_acceptance_criteria(
            story.get("acceptance_criteria", "[]")
        ),
        "story_id": story.get("id", ""),
        "priority": story.get("priority", "medium"),
    }

    return template.render(**context)


# ─── LLM plugin slot ──────────────────────────────────────────────────────────

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()  # "openai" | "ollama" | "gemini" | "none"
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash")


async def generate_with_llm(story: dict) -> Optional[str]:
    """
    Generate Gherkin using an LLM provider.
    Currently supported: openai, ollama, gemini.

    Set environment variables:
      LLM_PROVIDER=gemini    LLM_API_KEY=...
      LLM_PROVIDER=openai    LLM_API_KEY=sk-...
      LLM_PROVIDER=ollama    LLM_BASE_URL=http://localhost:11434

    Returns None if no provider is configured (falls back to Jinja2).
    """
    if LLM_PROVIDER == "none":
        return None

    template_name = _detect_template(story)
    prompt = _build_llm_prompt(story, template_name)

    if LLM_PROVIDER == "openai":
        return await _call_openai(prompt)
    elif LLM_PROVIDER == "ollama":
        return await _call_ollama(prompt)
    elif LLM_PROVIDER == "gemini":
        return await _call_gemini(prompt)
    else:
        return None



def _build_llm_prompt(story: dict, template_name: str) -> str:
    """Build the LLM prompt for Gherkin generation with RAG context."""
    criteria = _parse_acceptance_criteria(story.get("acceptance_criteria", "[]"))
    criteria_text = "\n".join(f"  - {c}" for c in criteria)

    rag_context = ""
    try:
        template_path = TEMPLATES_DIR / template_name
        if template_path.exists():
            rag_context = f"\nReference Template (use this structure/style as a guide):\n```gherkin\n{template_path.read_text()}\n```\n"
    except Exception:
        pass

    return f"""You are a QA expert. Generate a complete Gherkin feature file for the following user story.
Use proper Given/When/Then syntax. Include at least 2 scenarios: a happy path and an error/negative path.
{rag_context}
User Story:
  Actor: {story.get('actor')}
  Action: {story.get('action')}
  Goal: {story.get('goal')}
  Priority: {story.get('priority')}
  Acceptance Criteria:
{criteria_text}

Target application: SauceDemo (https://www.saucedemo.com)
Return ONLY the Gherkin feature file content, nothing else. Do not wrap in markdown tags if possible.
"""


async def _call_openai(prompt: str) -> Optional[str]:
    """Call OpenAI API for Gherkin generation."""
    try:
        import httpx
        api_key = os.getenv("LLM_API_KEY", "")
        if not api_key:
            return None

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.3,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None  # Fall back to Jinja2


async def _call_ollama(prompt: str) -> Optional[str]:
    """Call local Ollama server (CodeLlama / Mistral) for Gherkin generation."""
    try:
        import httpx
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={
                    "model": LLM_MODEL,  # e.g. "codellama" or "mistral"
                    "prompt": prompt,
                    "stream": False,
                },
            )
            return resp.json().get("response", "").strip()
    except Exception:
        return None  # Fall back to Jinja2


async def _call_gemini(prompt: str) -> Optional[str]:
    """Call Google Gemini API for Gherkin generation."""
    try:
        import google.generativeai as genai
        api_key = os.getenv("LLM_API_KEY", "")
        if not api_key:
            return None
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(LLM_MODEL)
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        
        # Clean up markdown tags if present
        if text.startswith("```gherkin"):
            text = text[10:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        return text.strip()
    except Exception as e:
        print(f"Gemini generation error: {e}")
        return None


# ─── Main public function ─────────────────────────────────────────────────────

async def generate_gherkin(story: dict) -> tuple[str, str]:
    """
    Generate Gherkin for a user story.
    Tries LLM first if configured; falls back to Jinja2.

    Returns:
        (gherkin_text, generator_name) where generator_name is "jinja2" or "llm"
    """
    # Try LLM if configured
    if LLM_PROVIDER != "none":
        llm_result = await generate_with_llm(story)
        if llm_result:
            return llm_result, "llm"

    # Default: Jinja2
    return generate_with_jinja2(story), "jinja2"
