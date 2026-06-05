"""
pom/pam/login_page.py — PAM Vault Login Page Object
─────────────────────────────────────────────────────
Example concrete implementation showing how executor.py
dynamically instantiates this class via PageFactory.

Receives payload:
  {
    "target_app": "EPM",
    "module":     "login",
    "target_url": "https://pam.company.local/login",
    "credentials": {"username": "...", "password": "..."}
  }
"""

from __future__ import annotations
from agent.pom.base_page import BasePage


class PAMLoginPage(BasePage):
    """
    Validates that the PAM vault login screen is reachable and
    accepts valid credentials, reporting the result.
    """

    async def run(self) -> str:
        creds = self.payload.get("credentials", {})
        username = creds.get("username", "")
        password = creds.get("password", "")

        try:
            await self._start(headless=True)
            await self.navigate()

            title = await self._page.title()

            # ── Step 1: Locate the username field ────────────────────
            user_field = await self._page.query_selector(
                "input[name='username'], input[type='text'], input[id*='user'], input[placeholder*='user' i]"
            )
            if not user_field:
                return f"FAILED: Could not locate username input on {self.target_url}"

            # ── Step 2: Fill credentials ─────────────────────────────
            await user_field.fill(username)
            pass_field = await self._page.query_selector(
                "input[name='password'], input[type='password']"
            )
            if pass_field:
                await pass_field.fill(password)

            # ── Step 3: Submit ───────────────────────────────────────
            submit = await self._page.query_selector(
                "button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign In')"
            )
            if submit:
                await submit.click()
                await self._page.wait_for_load_state("networkidle", timeout=10_000)

            post_url = self._page.url
            return (
                f"SUCCESS: Login flow completed. "
                f"Page title: '{title}' | Post-submit URL: {post_url}"
            )

        except Exception as e:
            return f"ERROR: {e}"
        finally:
            await self._stop()
