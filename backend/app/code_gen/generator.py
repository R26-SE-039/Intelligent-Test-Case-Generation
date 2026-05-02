import os
from typing import Optional
import httpx

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

async def generate_test_suite(
    gherkin_texts: list[str],
    url: str,
    mode: str,
    framework: str
) -> Optional[str]:
    """
    Generate a complete test suite for the given Gherkin features.
    Supports Anthropic, Gemini, OpenAI.
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        raise ValueError("LLM_API_KEY environment variable is not set or loaded properly.")

    try:

        # Build prompt
        features_str = "\n\n".join(f"Feature {i+1}:\n{text}" for i, text in enumerate(gherkin_texts))
        
        mode_instruction = ""
        if mode == "dom":
            mode_instruction = f"The target URL is '{url}'. Since this is DOM-Aware mode, assume we have crawled the DOM. Use realistic standard CSS selectors (e.g., #user-name, #password) appropriate for a standard app if you can infer them, otherwise make your best logical guess for the elements."
        else:
            mode_instruction = "This is Abstract Mode. The target UI is not available yet. Please use clear placeholder locators (e.g. <<USERNAME_INPUT_PLACEHOLDER>>) in the code."

        framework_instructions = ""
        if framework == "selenium":
            framework_instructions = "Use Python with pytest and Selenium WebDriver."
        elif framework == "playwright":
            framework_instructions = "Use Python with pytest and playwright.sync_api."
        elif framework == "cypress":
            framework_instructions = "Use JavaScript with Cypress (cy.get, cy.visit, etc.)."

        prompt = f"""You are an expert QA Automation Engineer.
I have several Gherkin feature files for a project. I want you to write a single, complete test suite file combining the implementation for ALL of these features.

Target Framework: {framework_instructions}
Target URL: {url}
Mode Instructions: {mode_instruction}

Here are the Gherkin features:
{features_str}

Please generate the complete, ready-to-run automation code for all of the above features. Include necessary imports, setup/teardown (or fixtures/hooks like beforeEach/pytest.fixture), and map the Given/When/Then steps to code as best as possible.
Return ONLY the raw source code. Do not include markdown code block syntax (like ```python or ```javascript). Just the raw text.
"""

        if LLM_PROVIDER == "anthropic":
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 4096,
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"].strip()
        elif LLM_PROVIDER == "openai":
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
        else: # Default to Gemini
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(LLM_MODEL)
            response = await model.generate_content_async(prompt)
            text = response.text.strip()

        # Clean markdown if present
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 1 and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        return text
    except Exception as e:
        print(f"Error generating test suite: {e}")
        raise e
