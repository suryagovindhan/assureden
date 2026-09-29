"""Local, deterministic recorder. Review the exported file before promotion."""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CAPTURE_SCRIPT = r"""
(() => {
  if (window !== window.top) {
    window.__assuredenWarn('Frame interactions need manual authoring.').catch(() => {}); return;
  }
  if (window.__assuredenCapturing) return;
  window.__assuredenCapturing = true;
  function locators(el) {
    const result = [];
    const add = (type, value) => { if (value && value.length <= 1000) result.push({type, value,
      priority: result.length + 1, is_primary: result.length === 0, is_active: true, added_by: 'RECORDER'}); };
    add('TEST_ID', el.getAttribute('data-testid'));
    add('ID', el.id);
    add('ARIA_LABEL', el.getAttribute('aria-label'));
    const path = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.id) { path.unshift('#' + CSS.escape(node.id)); break; }
      const peers = node.parentElement ? [...node.parentElement.children].filter(x => x.tagName === node.tagName) : [node];
      path.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + (peers.indexOf(node) + 1) + ')');
    }
    add('CSS_SELECTOR', path.join(' > '));
    return result;
  }
  const send = (el, action, value = '', secret = false) => {
    window.__assuredenRecord({action, input_value: value, is_secret: secret, locators: locators(el)}).catch(() => {});
  };
  document.addEventListener('click', event => {
    const el = event.target.closest('button,a,input,select,textarea,[role="button"]') || event.target;
    if (el.matches('input,select,textarea')) return;
    send(el, 'CLICK');
  }, true);
  document.addEventListener('change', event => {
    const el = event.target;
    if (el.matches('input[type="file"],input[type="radio"],select[multiple]')) {
      window.__assuredenWarn('File, radio and multi-select inputs need manual authoring.').catch(() => {}); return;
    }
    if (el.matches('input[type="checkbox"]')) return send(el, el.checked ? 'CHECK' : 'UNCHECK');
    if (el.matches('select:not([multiple])')) return send(el, 'SELECT', el.value);
    if (el.matches('input,textarea')) {
      const secret = el.type === 'password';
      send(el, 'TYPE', secret ? '' : el.value, secret);
    }
  }, true);
})();
"""


class RecordingSession:
    def __init__(self, name, url):
        self.data = {"schema_version": 1, "name": name,
                     "warnings": [],
                     "steps": [{"action": "NAVIGATE", "input_value": url, "locators": [], "is_secret": False}]}

    async def attach(self, context):
        primary = None
        def note_page(page):
            nonlocal primary
            if primary is None:
                primary = page
            else:
                warn(None, "New tabs and popups need manual authoring.")
        def warn(source, message):
            if message not in self.data["warnings"] and len(self.data["warnings"]) < 20:
                self.data["warnings"].append(message[:200])
        context.on("page", note_page)
        await context.expose_binding("__assuredenWarn", warn)
        def capture(source, event):
            if source["page"] != primary or source["frame"] != source["page"].main_frame:
                return
            if len(self.data["steps"]) >= 500:
                warn(None, "Recording reached 500 steps; later actions were not captured.")
                return
            if event.get("is_secret"):
                event["input_value"] = "{{RECORDED_SECRET_" + str(len(self.data["steps"])) + "}}"
            self.data["steps"].append(event)
        await context.expose_binding("__assuredenRecord", capture)
        await context.add_init_script(CAPTURE_SCRIPT)


async def main():
    parser = argparse.ArgumentParser(description="Record a browser session for AssureDen Drafts")
    parser.add_argument("url")
    parser.add_argument("--name", default="Recorded test")
    parser.add_argument("--output", default="recording.json")
    parser.add_argument("--channel", default=None)
    args = parser.parse_args()
    if urlparse(args.url).scheme not in {"http", "https"}:
        parser.error("Use an HTTP or HTTPS URL")
    if Path(args.output).exists():
        parser.error("Output already exists; choose a new recording filename")
    recording = RecordingSession(args.name, args.url)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel=args.channel, headless=False)
            closed = asyncio.Event()
            browser.on("disconnected", lambda: closed.set())
            context = await browser.new_context()
            await recording.attach(context)
            page = await context.new_page()
            await page.goto(args.url)
            print("Recording. Finish inputs by leaving the field. Close the browser to save.", flush=True)
            await closed.wait()
    finally:
        Path(args.output).write_text(json.dumps(recording.data, indent=2), encoding="utf-8")
        print(f"Saved {len(recording.data['steps'])} steps to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
