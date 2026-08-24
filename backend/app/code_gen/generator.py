import os
import re
from typing import Optional
import httpx

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

async def generate_test_suite(
    gherkin_texts: list[str],
    url: str,
    mode: str,
    framework: str,
    dom_elements: Optional[list[dict]] = None,
) -> Optional[str]:
    """
    Generate a complete test suite for the given Gherkin features.
    Supports Anthropic, Gemini, OpenAI.

    When `dom_elements` is provided (Mode B with a successful crawl) the LLM is
    instructed to use those exact selectors instead of inventing them.
    Each element should look like:
        {"role": "login_button", "selector": "#login-button", "tag": "INPUT"}
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        raise ValueError("LLM_API_KEY environment variable is not set or loaded properly.")

    try:

        # Build prompt
        features_str = "\n\n".join(f"Feature {i+1}:\n{text}" for i, text in enumerate(gherkin_texts))
        scenario_titles: list[str] = []
        for text in gherkin_texts:
            scenario_titles.extend(
                m.group(1).strip()
                for m in re.finditer(r"^\s*Scenario(?: Outline)?:\s*(.+)$", text or "", re.M)
            )
        scenario_block = "\n".join(f"- {title}" for title in scenario_titles) or "- (none parsed)"

        mode_instruction = ""
        if mode == "dom":
            if dom_elements:
                rows = "\n".join(
                    f"  - role={e['role']:<32s} selector={e['selector']:<40s} tag={e.get('tag','')}"
                    + (f"  text={e['text']!r}" if e.get('text') else "")
                    for e in dom_elements
                )
                mode_instruction = (
                    f"The target URL is '{url}'. We crawled the live DOM and extracted these REAL elements. "
                    f"You MUST use these exact selectors in the generated code (do NOT invent or guess any other selectors):\n"
                    f"{rows}\n\n"
                    f"If a Gherkin step refers to an element not in this list, leave a clear TODO comment "
                    f"with the role you'd need (e.g. `# TODO: selector for 'add_to_cart_button' not crawled yet`)."
                )
            else:
                mode_instruction = (
                    f"The target URL is '{url}'. Since this is DOM-Aware mode but no crawled "
                    f"selectors were provided, use realistic standard CSS selectors and add a TODO comment."
                )
        else:
            mode_instruction = "This is Abstract Mode. The target UI is not available yet. Please use clear placeholder locators (e.g. <<USERNAME_INPUT_PLACEHOLDER>>) in the code."

        framework_instructions = ""
        if framework == "selenium":
            framework_instructions = "Use Python with pytest and Selenium WebDriver."
        elif framework == "playwright":
            framework_instructions = "Use Python with pytest and playwright.sync_api."
        elif framework == "cypress":
            framework_instructions = "Use JavaScript with Cypress (cy.get, cy.visit, etc.)."

        runtime_constraints = ""
        if framework == "playwright":
            runtime_constraints = (
                "\nRuntime constraints (must follow):\n"
                "- Generated Playwright tests must run in Linux CI without a display server.\n"
                "- Launch browser in headless mode (headless=True or default headless launch).\n"
                "- Do NOT force headed mode (headless=False).\n"
            )

        saucedemo_knowledge = ""
        if "saucedemo.com" in (url or "").lower():
            saucedemo_knowledge = (
                "\nSauceDemo behavior rules (must follow exactly):\n"
                "- Login success URL is /inventory.html.\n"
                "- All pages except the login page require an authenticated session. Visiting /inventory.html, "
                "/cart.html, or /checkout-step-*.html directly WITHOUT logging in first redirects back to the login "
                "page, so element selectors (e.g. #add-to-cart-<item>) will never appear and clicks time out. "
                "EVERY test that touches the cart, inventory, or checkout MUST log in first (go to '/', fill "
                "credentials, click #login-button) before navigating or clicking. Do NOT page.goto a post-login URL "
                "as the first action of a test.\n"
                "- Invalid login error text is exactly: \"Epic sadface: Username and password do not match any user in this service\".\n"
                "- Login page URL checks must tolerate optional trailing slash.\n"
                "- When cart is empty, .shopping_cart_badge is usually NOT visible; do NOT assert badge text \"0\".\n"
                "- Use .shopping_cart_link for cart navigation.\n"
                "- The add-to-cart button TOGGLES: after clicking #add-to-cart-<item> the button is replaced by "
                "#remove-<item>. The add selector no longer exists, so clicking it again will hang until timeout.\n"
                "- For an \"add item already in cart\" scenario, click add-to-cart exactly ONCE, then assert the button "
                "became #remove-<item> (visible) and .shopping_cart_badge text stays \"1\". Never click the same "
                "add-to-cart selector twice.\n"
                "- For a \"remove item not in cart\" scenario, do not assume #remove-<item> exists; guard the click "
                "and assert .shopping_cart_badge is not visible.\n"
                "- Checkout is a MULTI-STEP flow: #continue only advances to the overview page (checkout-step-two). "
                "To complete the order and reveal .complete-header (\"Thank you for your order!\"), you MUST also "
                "click #finish. A checkout helper that stops at #continue will never reach the confirmation.\n"
                "- For successful checkout, postal code must be non-empty (e.g., \"12345\").\n"
                "- For missing postal code, keep postal empty and expect exact error: \"Error: Postal Code is required\".\n"
            )

            if framework == "playwright":
                saucedemo_knowledge += (
                    "\nSauceDemo Playwright reference implementations — copy this logic EXACTLY. "
                    "Do NOT invent selector-mangling helpers or transform selector strings:\n"
                    "```python\n"
                    "def add_to_cart(page, add_selector):\n"
                    "    # add_selector is a full id, e.g. \"#add-to-cart-sauce-labs-backpack\"\n"
                    "    page.click(add_selector)\n"
                    "\n"
                    "def remove_from_cart(page, remove_selector):\n"
                    "    # Click the remove id DIRECTLY. Never split/rebuild it (no split('-')[-1]).\n"
                    "    # remove_selector is a full id, e.g. \"#remove-sauce-labs-backpack\"\n"
                    "    page.click(remove_selector)\n"
                    "```\n"
                    "For \"add item already in cart\" — click add ONCE (the button then toggles to remove):\n"
                    "```python\n"
                    "    page.click(\"#add-to-cart-sauce-labs-backpack\")\n"
                    "    assert page.locator(\"#remove-sauce-labs-backpack\").is_visible()\n"
                    "    assert page.locator(\".shopping_cart_badge\").inner_text() == \"1\"\n"
                    "```\n"
                    "For \"remove item not in cart\" — guard the click, the remove id may not exist:\n"
                    "```python\n"
                    "    if page.locator(\"#remove-sauce-labs-backpack\").is_visible():\n"
                    "        page.click(\"#remove-sauce-labs-backpack\")\n"
                    "    assert not page.locator(\".shopping_cart_badge\").is_visible()\n"
                    "```\n"
                )

        test_design_rules = (
            "\nTest design and implementation rules (must follow):\n"
            "- Never call one test function from another test function.\n"
            "- Put shared actions in helpers and call helpers from tests.\n"
            "- Use a fresh browser context/page per test for isolation.\n"
            "- If a helper already performs an action (e.g., click Continue), do not repeat it in test body.\n"
            "- Prefer robust selectors (data-test or known stable selectors) over brittle text-only assumptions.\n"
        )

        prompt = f"""You are an expert QA Automation Engineer.
I have several Gherkin feature files for a project. I want you to write a single, complete test suite file combining the implementation for ALL of these features.

Target Framework: {framework_instructions}
Target URL: {url}
Mode Instructions: {mode_instruction}
{runtime_constraints}
{saucedemo_knowledge}
{test_design_rules}

Here are the Gherkin features:
{features_str}

Strict scope rules (must follow):
1. Generate tests ONLY for the scenarios explicitly listed in the input Gherkin.
2. Do NOT add extra scenarios from product knowledge or assumptions.
3. Do NOT include unrelated flow logic (e.g., cart/checkout/search) unless those scenarios are explicitly present.
4. Keep selectors and helper utilities limited to what the listed scenarios need.

Scenario titles to implement:
{scenario_block}

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
