"""
agent/executor.py — AssureDen Command Executor (Phase 3)
─────────────────────────────────────────────────────────
Accepts two payload formats:

1. RunRequest (new QA-first) — carries structured steps with ranked_locators:
   {
     "type":           "run_steps",
     "run_id":         "uuid",
     "environment_id": "uuid",
     "base_url":       "https://app.company.com",
     "steps":          [ { TestStep dicts with ranked_locators, action, ... } ],
     "resolved_inputs":{ "step-uuid": "resolved-value", ... }  # pre-resolved server-side
   }

2. Legacy POM dispatch (kept for backward compat):
   {
     "type":       "pom_run",
     "target_app": "EPM",
     "module":     "Users",
     "target_url": "https://..."
   }

Returns:
   { "status": "SUCCESS|FAILED|ERROR", "steps": [ StepTelemetry dicts ] }
"""

from __future__ import annotations
import asyncio
import json
import traceback
from typing import Any

from playwright.async_api import async_playwright

from agent.core.auth_manager import AuthManager
from agent.core.step_runner  import run_step


# ─────────────────────────────────────────────────────────────────────────────
# RunRequest handler  (preferred format)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_steps(payload: dict) -> dict:
    """
    Executes a structured list of TestSteps via the Resilient Locator Engine.
    Returns per-step telemetry to be stored in RunStepExecution.
    """
    run_id          = payload.get("run_id", "local")
    env_id          = payload.get("environment_id", "default")
    base_url        = payload.get("base_url", "about:blank")
    steps           = payload.get("steps", [])
    resolved_inputs = payload.get("resolved_inputs", {})
    headless        = payload.get("headless", True)
    server_api      = payload.get("server_api", "http://127.0.0.1:8001")

    print(f"[Executor] RunRequest run_id={run_id} | {len(steps)} steps | URL={base_url}")

    step_results: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        # Auth state injection
        auth    = AuthManager(environment_id=env_id, server_api=server_api)
        context = await auth.prepare_context(browser)

        page = await context.new_page()
        page.on("console", lambda m: print(f"  [browser:{m.type}] {m.text}"))

        # Navigate to base URL first
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            await browser.close()
            return {"status": "ERROR", "detail": f"Failed to navigate to {base_url}: {e}", "steps": []}

        # Execute each step
        overall_ok = True
        for step in steps:
            resolved_val = resolved_inputs.get(step.get("id", ""), "")
            tel = await run_step(page, step, resolved_val)
            step_results.append(tel.as_dict())

            icon = "✓" if tel.status == "SUCCESS" else "✗"
            healed = " [HEALED]" if tel.fallback_success else ""
            print(f"  {icon} Step {step.get('sequence_order','?')} — {tel.status}{healed} "
                  f"via '{tel.successful_locator}' ({tel.execution_time_ms}ms)")

            if tel.status == "FAILED":
                overall_ok = False
                print(f"    ↳ Error: {tel.error_message}")
                break

        # Optionally persist auth state after a successful run
        if overall_ok:
            await auth.save_state(context)

        await context.close()
        await browser.close()

    final_status = "SUCCESS" if overall_ok else "FAILED"
    print(f"[Executor] Run complete → {final_status}")
    return {"status": final_status, "run_id": run_id, "steps": step_results}


# ─────────────────────────────────────────────────────────────────────────────
# Legacy POM Dispatch  (backward compat)
# ─────────────────────────────────────────────────────────────────────────────

async def _pom_run(payload: dict) -> dict:
    """Resolve and run a legacy Page Object via PageFactory."""
    from agent.pom.page_factory import PageFactory
    target_app = payload.get("target_app")
    module     = payload.get("module")
    target_url = payload.get("target_url")

    if not all([target_app, module, target_url]):
        return {"status": "ERROR", "detail": "Missing: target_app, module, target_url", "steps": []}

    try:
        page_class = PageFactory.resolve(target_app=target_app, module=module)
        if page_class is None:
            return {"status": "ERROR",
                    "detail": f"No handler for app='{target_app}' module='{module}'", "steps": []}
        page   = page_class(target_url=target_url, payload=payload)
        result = await page.run()
        return {"status": "SUCCESS", "detail": str(result), "steps": []}
    except Exception as e:
        return {"status": "FAILED", "detail": str(e), "steps": [],
                "stack_trace": traceback.format_exc()}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def execute(payload: dict) -> dict:
    """Route to the correct handler based on payload type."""
    ptype = payload.get("type", "pom_run")
    if ptype == "run_steps":
        return await _run_steps(payload)
    else:
        return await _pom_run(payload)
