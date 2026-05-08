"""
Set-of-Mark (SoM) overlay — research technique from Yang et al. 2023.

The agent doesn't pick CSS selectors. It looks at a screenshot where every
clickable element has a numbered red box on top of it, then says
"click element 7". The Python side then resolves "7" → real selector.

This avoids selector hallucination, which is the #1 failure mode of
LLM-driven browser agents that operate on raw HTML.
"""

# Returns a list of {id, tag, selector, text, role, bbox} for every
# visible interactable element, AND draws numbered red boxes on top of them.
# Boxes are drawn by appending an absolutely-positioned <div> overlay so
# the original page DOM is not mutated.
SOM_INJECT_SCRIPT = r"""
() => {
  // Remove any prior overlay from a previous step.
  const prior = document.getElementById('__nextgenqa_som_overlay__');
  if (prior) prior.remove();

  const overlay = document.createElement('div');
  overlay.id = '__nextgenqa_som_overlay__';
  overlay.style.cssText = `
    position: fixed; inset: 0; pointer-events: none; z-index: 2147483647;
  `;
  document.body.appendChild(overlay);

  const cssEscape = (s) =>
    (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, '\\$&');

  const buildSelector = (el) => {
    if (el.id) return '#' + cssEscape(el.id);
    const dt = el.getAttribute('data-testid');
    if (dt) return `[data-testid="${dt.replace(/"/g, '\\"')}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\"')}"]`;
    const aria = el.getAttribute('aria-label');
    if (aria) return `${el.tagName.toLowerCase()}[aria-label="${aria.replace(/"/g, '\\"')}"]`;
    let path = [];
    let node = el;
    while (node && node.nodeType === 1 && path.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id) { part = '#' + cssEscape(node.id); path.unshift(part); break; }
      const parent = node.parentElement;
      if (parent) {
        const sibs = Array.from(parent.children).filter(c => c.tagName === node.tagName);
        if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(node) + 1})`;
      }
      path.unshift(part);
      node = node.parentElement;
    }
    return path.join(' > ');
  };

  const isVisible = (el) => {
    if (!el.isConnected) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return false;
    if (rect.bottom < 0 || rect.right < 0) return false;
    if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
    const cs = window.getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return false;
    return true;
  };

  const candidates = document.querySelectorAll(
    'input, textarea, select, button, a[href], ' +
    '[role="button"], [role="link"], [role="textbox"], [role="searchbox"], [role="combobox"], [onclick]'
  );

  const elements = [];
  let counter = 0;
  const seen = new Set();

  candidates.forEach((el) => {
    if (!isVisible(el)) return;
    const sel = buildSelector(el);
    if (!sel || seen.has(sel)) return;
    seen.add(sel);

    counter += 1;
    const rect = el.getBoundingClientRect();

    // Draw a colored bounding box.
    const box = document.createElement('div');
    box.style.cssText = `
      position: fixed;
      left: ${rect.left}px;
      top: ${rect.top}px;
      width: ${rect.width}px;
      height: ${rect.height}px;
      border: 2px solid #ff3b30;
      box-sizing: border-box;
      pointer-events: none;
    `;
    overlay.appendChild(box);

    // Draw the numbered label badge in the top-left corner.
    const label = document.createElement('div');
    label.textContent = String(counter);
    label.style.cssText = `
      position: fixed;
      left: ${Math.max(0, rect.left - 2)}px;
      top: ${Math.max(0, rect.top - 18)}px;
      background: #ff3b30;
      color: white;
      font: bold 12px/1 ui-sans-serif, system-ui, sans-serif;
      padding: 2px 5px;
      border-radius: 3px;
      pointer-events: none;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    `;
    overlay.appendChild(label);

    // Capture meta for the agent.
    const attrs = {};
    for (const a of el.attributes) {
      if (['id','name','type','placeholder','aria-label','role','data-testid','href','value'].includes(a.name)) {
        attrs[a.name] = a.value;
      }
    }

    elements.push({
      id: counter,
      tag: el.tagName.toLowerCase(),
      selector: sel,
      text: (el.innerText || el.value || '').trim().slice(0, 80),
      role: attrs.role || el.getAttribute('type') || el.tagName.toLowerCase(),
      bbox: { x: Math.round(rect.left), y: Math.round(rect.top),
              w: Math.round(rect.width), h: Math.round(rect.height) },
      attrs,
    });
  });

  return elements;
}
"""


SOM_REMOVE_SCRIPT = r"""
() => {
  const prior = document.getElementById('__nextgenqa_som_overlay__');
  if (prior) prior.remove();
  return true;
}
"""
