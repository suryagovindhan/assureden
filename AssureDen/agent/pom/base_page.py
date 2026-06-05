"""
agent/pom/base_page.py — Abstract Base Page (Phase 3 upgrade)
──────────────────────────────────────────────────────────────
Integrates:
  • AuthManager  — reuses saved login state per environment
  • step_runner  — resilient locator strategy for all steps
  • Evidence capture on failure (screenshots already handled inside step_runner)
"""

from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from agent.core.auth_manager import AuthManager


class BasePage(ABC):
    """
    Abstract base for all Page Objects.

    Subclasses must implement:
      • run() → list[dict]  — returns list of StepTelemetry dicts
    """

    def __init__(self, target_url: str, payload: dict):
        self.target_url     = target_url
        self.payload        = payload
        self.environment_id = payload.get("environment_id", "default")
        self.server_api     = payload.get("server_api", "http://127.0.0.1:8001")
        
        self._pw:      object         | None = None
        self._browser: Browser        | None = None
        self._context: BrowserContext | None = None
        self._page:    Page           | None = None
        self._auth:    AuthManager    | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def _start(self, headless: bool = True):
        """Launch Playwright and open a new page, reusing auth state if available."""
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=headless)
        
        # Auth state injection
        self._auth    = AuthManager(
            environment_id=self.environment_id,
            server_api=self.server_api,
        )
        self._context = await self._auth.prepare_context(self._browser)
        
        # Enable console log capture (forwarded to agent stdout for debugging)
        self._page = await self._context.new_page()
        self._page.on("console", lambda msg: print(f"  [browser:{msg.type}] {msg.text}"))

    async def _stop(self, save_auth: bool = False):
        """Close browser cleanly, optionally persisting auth state."""
        if save_auth and self._auth and self._context:
            await self._auth.save_state(self._context)
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # ── Shared Helpers ───────────────────────────────────────────────────────

    async def navigate(self, url: str | None = None):
        """Navigate to target_url or override, waiting for DOM ready."""
        await self._page.goto(url or self.target_url, wait_until="domcontentloaded")

    async def screenshot(self, path: str = "screenshot.png"):
        """Capture a full-page screenshot for evidence."""
        await self._page.screenshot(path=path, full_page=True)

    # ── Abstract Interface ───────────────────────────────────────────────────

    @abstractmethod
    async def run(self) -> list[dict]:
        """
        Execute the full test workflow.
        Must return a list of StepTelemetry.as_dict() results.
        """
        ...

    # ── Convenience: run all structured steps from payload ───────────────────

    async def run_structured_steps(self, resolved_inputs: dict[str, str]) -> list[dict]:
        """
        Execute steps sent directly in the payload (from RunRequest dispatch).
        resolved_inputs: {step_id: resolved_value} pre-resolved by DataResolver on server.
        """
        from agent.core.step_runner import run_step
        results = []
        steps   = self.payload.get("steps", [])
        for step in steps:
            resolved_val = resolved_inputs.get(step.get("id", ""), "")
            print(f"  [Step {step.get('sequence_order', '?')}] action={step.get('action')} locators={step.get('ranked_locators', [])[:1]}")
            tel = await run_step(self._page, step, resolved_val)
            results.append(tel.as_dict())
            status_icon = "✓" if tel.status == "SUCCESS" else "✗"
            healed_note = " [HEALED]" if tel.fallback_success else ""
            print(f"  {status_icon} {tel.status}{healed_note} in {tel.execution_time_ms}ms via '{tel.successful_locator}'")
            if tel.status == "FAILED":
                print(f"    Error: {tel.error_message}")
                break  # Stop executing remaining steps on failure
        return results
