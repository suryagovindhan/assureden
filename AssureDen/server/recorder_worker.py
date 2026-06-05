"""
server/recorder_worker.py — Standalone Playwright recorder process
───────────────────────────────────────────────────────────────────
Run as a subprocess by sandbox_ws.py. Communicates via stdout (JSON lines).
This completely avoids the greenlet/asyncio thread conflict.

Protocol:
  Server reads stdout line by line.
  Each line is a JSON object: {"type": "...", ...}

  Types emitted:
    {"type": "ready"}
    {"type": "step", "step": {...}, "sequence": N}
    {"type": "script", "script": "..."}
    {"type": "all_steps", "steps": [...]}
    {"type": "error", "detail": "..."}
    {"type": "closed"}   — browser closed by user

  stdin:
    "stop\n"  → graceful stop
"""

import json
import sys
import time
import threading

def emit(obj: dict):
    print(json.dumps(obj), flush=True)

def main():
    if len(sys.argv) < 2:
        emit({"type": "error", "detail": "Usage: recorder_worker.py <target_url>"})
        return

    target_url = sys.argv[1]
    all_steps  = []
    stop_event = threading.Event()

    # ── stdin listener (watches for "stop" command) ──────────────────
    def _stdin_watcher():
        try:
            for line in sys.stdin:
                if line.strip() == "stop":
                    stop_event.set()
                    break
        except Exception:
            stop_event.set()

    threading.Thread(target=_stdin_watcher, daemon=True).start()

    # ── Playwright session ───────────────────────────────────────────
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(ignore_https_errors=True)

            # Inject the step-capturing JS before every page load
            context.add_init_script("""
(function() {
  if (window.__assureden_recorder_active) return;
  window.__assureden_recorder_active = true;

  function getStableCssPath(el) {
    if (!el || el === document.body) return 'body';
    const parts = [];
    let cur = el;
    while (cur && cur !== document.body) {
      let sel = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + cur.id); break; }
      const sibs = Array.from(cur.parentNode?.children || []).filter(s => s.tagName === cur.tagName);
      if (sibs.length > 1) sel += ':nth-of-type(' + (sibs.indexOf(cur) + 1) + ')';
      parts.unshift(sel);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function getAriaName(el) {
    return el.getAttribute('aria-label') || el.getAttribute('title') ||
           el.getAttribute('placeholder') || el.innerText?.trim().slice(0, 50) || '';
  }

  function getLabelText(el) {
    if (el.id) {
      const lbl = document.querySelector('label[for="' + el.id + '"]');
      if (lbl) return lbl.innerText.trim();
    }
    const p = el.closest('label');
    if (p) return p.innerText.trim();
    const prev = el.previousElementSibling;
    if (prev && prev.tagName === 'LABEL') return prev.innerText.trim();
    return '';
  }

  function buildLocators(el) {
    const locs = [];
    const tid = el.getAttribute('data-testid') || el.getAttribute('data-test-id');
    if (tid) locs.push("[data-testid='" + tid + "']");
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const aname = getAriaName(el);
    if (aname) locs.push(role + '[aria-label="' + aname.slice(0,40) + '"]');
    const lbl = getLabelText(el);
    if (lbl) locs.push('label:has-text("' + lbl.slice(0,30) + '") + ' + el.tagName.toLowerCase());
    if (el.name) locs.push(el.tagName.toLowerCase() + '[name="' + el.name + '"]');
    if (el.id) locs.push('#' + el.id);
    locs.push(getStableCssPath(el));
    return [...new Set(locs)];
  }

  function buildMeta(el) {
    return {
      label: getLabelText(el),
      inner_text: el.innerText?.trim().slice(0, 80) || '',
      placeholder: el.getAttribute('placeholder') || '',
      tag: el.tagName.toLowerCase(),
      dom_hierarchy: (el.parentElement?.tagName.toLowerCase() || '') + ' > ' + el.tagName.toLowerCase()
    };
  }

  function dispatch(data) {
    window.__assureden_steps = window.__assureden_steps || [];
    window.__assureden_steps.push(data);
  }

  document.addEventListener('click', function(e) {
    const el = e.target;
    if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') return;
    dispatch({ action: 'CLICK', ranked_locators: buildLocators(el),
      fallback_metadata: buildMeta(el), input_source_type: null, input_reference: null,
      expected_condition: { condition: 'network_idle' }, timeout_ms: 5000, retry_policy: 2 });
  }, true);

  document.addEventListener('change', function(e) {
    const el = e.target;
    if (!el || !('value' in el)) return;
    if (!['input','textarea','select'].includes(el.tagName.toLowerCase())) return;
    const action = el.tagName.toLowerCase() === 'select' ? 'SELECT' : 'FILL';
    dispatch({ action, ranked_locators: buildLocators(el),
      fallback_metadata: buildMeta(el), input_source_type: 'FIXED',
      input_reference: el.value || '', expected_condition: null,
      timeout_ms: 5000, retry_policy: 1 });
  }, true);
})();
""")

            page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            emit({"type": "ready"})

            seq = 1
            while not stop_event.is_set():
                try:
                    if page.is_closed():
                        stop_event.set()
                        break
                except Exception:
                    stop_event.set()
                    break

                # Drain captured steps from the page
                try:
                    steps = page.evaluate("""() => {
                        const s = window.__assureden_steps || [];
                        window.__assureden_steps = [];
                        return s;
                    }""")
                    for step in (steps or []):
                        step["sequence_order"] = seq
                        all_steps.append(step)
                        emit({"type": "step", "step": step, "sequence": seq})
                        seq += 1
                except Exception:
                    pass

                time.sleep(0.4)

            # Build script
            lines = [
                "from playwright.sync_api import sync_playwright", "",
                "def run():",
                "    with sync_playwright() as pw:",
                "        browser = pw.chromium.launch(headless=False)",
                "        context = browser.new_context(ignore_https_errors=True)",
                "        page = context.new_page()",
                f"        page.goto({target_url!r})",
                "",
            ]
            for s in all_steps:
                locs = s.get("ranked_locators", [])
                sel  = locs[0] if locs else "body"
                act  = s.get("action", "CLICK")
                ref  = s.get("input_reference", "") or ""
                if act == "CLICK":
                    lines.append(f"        page.locator({sel!r}).click()")
                elif act == "FILL":
                    lines.append(f"        page.locator({sel!r}).fill({ref!r})")
                elif act == "SELECT":
                    lines.append(f"        page.locator({sel!r}).select_option({ref!r})")
            lines += ["        browser.close()", "", "if __name__ == '__main__':", "    run()"]
            emit({"type": "script", "script": "\n".join(lines)})
            emit({"type": "all_steps", "steps": all_steps})

            try: page.close()
            except Exception: pass
            try: context.close()
            except Exception: pass
            try: browser.close()
            except Exception: pass

    except Exception as e:
        emit({"type": "error", "detail": str(e)})

    emit({"type": "closed"})

if __name__ == "__main__":
    main()
