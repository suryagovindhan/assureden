"""
agent/core/step_runner.py — Resilient Step Execution Engine
────────────────────────────────────────────────────────────
Heart of Phase 3. Executes a single TestStep with:

  1. Ranked locator strategy (try [0], [1], [2]…)
  2. Smart waits instead of static sleeps
  3. Retry policy (per step, configurable)
  4. Full attempt log (who tried what, in what order)
  5. Healed-step detection (fallback_success flag)
  6. Failure evidence capture (screenshot, DOM snapshot)
  7. Input masking for secrets

Returns a StepTelemetry dict understood by the server's RunStepExecution model.
"""

from __future__ import annotations
import asyncio
import base64
import json
import time
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any

from playwright.async_api import Page, Error as PlaywrightError


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry Data Shape (mirrors RunStepExecution model)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StepTelemetry:
    step_id:              str
    status:               str  = "SUCCESS"          # SUCCESS | FAILED | SKIPPED
    primary_success:      bool = True               # ranked_locators[0] worked
    fallback_success:     bool = False              # a secondary locator worked (HEALED)
    failed_all:           bool = False
    locators_attempted:   list = field(default_factory=list)
    successful_locator:   str  = ""
    retries_used:         int  = 0
    execution_time_ms:    int  = 0
    input_masked:         str  = ""                 # resolved value, secrets replaced
    error_message:        str  = ""
    stack_trace:          str  = ""
    screenshot_b64:       str  = ""                 # base64 PNG on failure
    dom_snapshot:         str  = ""                 # outer HTML of body on failure

    def as_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Smart Wait Strategies
# ─────────────────────────────────────────────────────────────────────────────

async def _smart_wait(page: Page, condition: dict | None, timeout_ms: int):
    """
    Execute a smart wait based on the step's expected_condition config.
    Supported conditions:
      {"condition": "network_idle"}      — wait for no network activity
      {"condition": "dom_stable"}        — wait for DOM to stop mutating
      {"condition": "element_visible",   — wait for a selector to appear
       "selector": "#result"}
      {"condition": "url_contains",
       "value": "/dashboard"}
    Falls back to a short fixed wait if condition is empty.
    """
    if not condition:
        await page.wait_for_timeout(300)  # minimal stabilisation wait
        return

    c = condition.get("condition", "")

    if c == "network_idle":
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)

    elif c == "dom_stable":
        # Poll until DOM stops changing for 300ms
        prev = ""
        for _ in range(20):
            html = await page.content()
            if html == prev:
                break
            prev = html
            await asyncio.sleep(0.3)

    elif c == "element_visible":
        sel = condition.get("selector", "body")
        await page.wait_for_selector(sel, state="visible", timeout=timeout_ms)

    elif c == "url_contains":
        value = condition.get("value", "")
        for _ in range(int(timeout_ms / 500)):
            if value in page.url:
                return
            await asyncio.sleep(0.5)
        raise TimeoutError(f"URL never contained '{value}' within {timeout_ms}ms")

    else:
        await page.wait_for_timeout(300)


# ─────────────────────────────────────────────────────────────────────────────
# Evidence Capture
# ─────────────────────────────────────────────────────────────────────────────

async def _capture_failure_evidence(page: Page) -> tuple[str, str]:
    """Returns (screenshot_b64, dom_snapshot_str)."""
    screenshot_b64 = ""
    dom_snapshot   = ""
    try:
        png = await page.screenshot(full_page=True)
        screenshot_b64 = base64.b64encode(png).decode()
    except Exception:
        pass
    try:
        dom_snapshot = await page.inner_html("body")
    except Exception:
        pass
    return screenshot_b64, dom_snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Locator Resolution
# ─────────────────────────────────────────────────────────────────────────────

async def _try_locator(page: Page, selector: str, action: str,
                       value: str, timeout_ms: int) -> bool:
    """
    Attempt a single Playwright locator action.
    Returns True on success, False on any Playwright error.
    """
    try:
        loc = page.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout_ms)

        action_upper = action.upper()
        if action_upper == "CLICK":
            await loc.click(timeout=timeout_ms)
        elif action_upper == "FILL":
            await loc.fill(value, timeout=timeout_ms)
        elif action_upper == "SELECT":
            await loc.select_option(value, timeout=timeout_ms)
        elif action_upper == "CHECK":
            await loc.check(timeout=timeout_ms)
        elif action_upper == "UNCHECK":
            await loc.uncheck(timeout=timeout_ms)
        elif action_upper == "ASSERT_VISIBLE":
            # Already proven visible by wait_for above
            pass
        elif action_upper == "ASSERT_TEXT":
            text = await loc.inner_text()
            if value not in text:
                raise AssertionError(f"Expected '{value}' in text, got '{text}'")
        else:
            raise ValueError(f"Unknown action: {action}")

        return True

    except (PlaywrightError, AssertionError, ValueError, TimeoutError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATE (special case — no locator needed)
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_navigate(page: Page, value: str, expected_condition: dict | None,
                             timeout_ms: int) -> None:
    await page.goto(value, wait_until="domcontentloaded", timeout=timeout_ms)
    await _smart_wait(page, expected_condition, timeout_ms)


# ─────────────────────────────────────────────────────────────────────────────
# Main Step Runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_step(
    page: Page,
    step: dict,
    resolved_value: str = "",
) -> StepTelemetry:
    """
    Execute a single TestStep dict against a live Playwright Page.

    step dict shape (mirrors TestStep model):
      {
        "id":                 "uuid",
        "action":             "FILL",
        "ranked_locators":    ["[data-testid='x']", "input[name='x']", "#x"],
        "expected_condition": {"condition": "network_idle"},
        "timeout_ms":         5000,
        "retry_policy":       2,
      }

    resolved_value: the fully-resolved input (from DataResolver; secrets masked).
    """
    step_id           = step.get("id", "unknown")
    action            = step.get("action", "CLICK")
    ranked_locators   = step.get("ranked_locators") or []
    expected_condition= step.get("expected_condition")
    timeout_ms        = step.get("timeout_ms", 5000)
    max_retries       = step.get("retry_policy", 1)

    tel = StepTelemetry(step_id=step_id, input_masked=resolved_value)
    start = time.monotonic()

    # ── Special actions that don't use locators ──────────────────────────────
    if action.upper() == "NAVIGATE":
        for attempt in range(max_retries):
            try:
                await _execute_navigate(page, resolved_value or step.get("url", ""), expected_condition, timeout_ms)
                tel.status = "SUCCESS"
                tel.retries_used = attempt
                tel.execution_time_ms = int((time.monotonic() - start) * 1000)
                return tel
            except Exception as e:
                if attempt == max_retries - 1:
                    tel.status         = "FAILED"
                    tel.failed_all     = True
                    tel.error_message  = str(e)
                    tel.stack_trace    = traceback.format_exc()
                    tel.screenshot_b64, tel.dom_snapshot = await _capture_failure_evidence(page)
                    tel.execution_time_ms = int((time.monotonic() - start) * 1000)
                    return tel

    if not ranked_locators:
        tel.status        = "FAILED"
        tel.failed_all    = True
        tel.error_message = f"No locators provided for action '{action}' (step {step_id})"
        tel.execution_time_ms = int((time.monotonic() - start) * 1000)
        return tel

    # ── Ranked Locator Strategy ──────────────────────────────────────────────
    # For each retry attempt, walk the full locator list
    for attempt in range(max_retries):
        tel.retries_used = attempt
        locator_succeeded = False

        for idx, selector in enumerate(ranked_locators):
            tel.locators_attempted.append(selector)

            ok = await _try_locator(page, selector, action, resolved_value, timeout_ms)
            if ok:
                tel.successful_locator = selector
                tel.primary_success    = (idx == 0)
                tel.fallback_success   = (idx > 0)      # ← HEALED STEP FLAG
                locator_succeeded      = True
                break  # Stop trying locators once one works

        if locator_succeeded:
            tel.status = "SUCCESS"
            # Apply smart wait after the action
            try:
                await _smart_wait(page, expected_condition, timeout_ms)
            except Exception:
                pass  # Post-action wait failure is non-fatal
            break

        # All locators failed this attempt — wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(1.5)

    # ── Determine final outcome ──────────────────────────────────────────────
    if tel.status != "SUCCESS":
        tel.status    = "FAILED"
        tel.failed_all= True
        tel.primary_success = False

        try:
            # Best-effort: try to get a useful error from the last locator
            await page.locator(ranked_locators[-1]).first.wait_for(
                state="visible", timeout=1000
            )
        except PlaywrightError as e:
            tel.error_message = str(e)
        except Exception as e:
            tel.error_message = str(e)

        tel.stack_trace    = traceback.format_exc()
        tel.screenshot_b64, tel.dom_snapshot = await _capture_failure_evidence(page)

    tel.execution_time_ms = int((time.monotonic() - start) * 1000)
    return tel
