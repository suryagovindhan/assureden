"""
agent/core/auth_manager.py — Auth State Management
────────────────────────────────────────────────────
Saves and restores Playwright browser_context storage_state (cookies, localStorage).
Allows the agent to skip logins across test runs.

Usage:
    auth = AuthManager(environment_id="env-123", server_api="http://127.0.0.1:8001")
    context = await auth.prepare_context(browser)  # returns authenticated context
    # ... run tests ...
    await auth.save_state(context)  # persists for next run
"""

from __future__ import annotations
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from playwright.async_api import Browser, BrowserContext


class AuthManager:
    """
    Manages Playwright storage_state per environment.
    States are saved locally and optionally pushed to the server.
    """

    _STATE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".auth_states"
    )

    def __init__(self, environment_id: str, server_api: str = "http://127.0.0.1:8001"):
        self._env_id    = environment_id
        self._server    = server_api
        self._state_path= os.path.join(self._STATE_DIR, f"{environment_id}.json")
        os.makedirs(self._STATE_DIR, exist_ok=True)

    # ── Context preparation ─────────────────────────────────────────────────

    async def prepare_context(self, browser: Browser) -> BrowserContext:
        """
        Return a BrowserContext pre-loaded with saved auth state if available.
        If no state exists, returns a clean context.
        """
        if os.path.exists(self._state_path):
            state = self._load_state()
            if self._is_valid(state):
                print(f"[AuthManager] Reusing saved auth state for env={self._env_id}")
                return await browser.new_context(storage_state=self._state_path)

        print(f"[AuthManager] No valid auth state — returning clean context for env={self._env_id}")
        return await browser.new_context()

    async def save_state(self, context: BrowserContext) -> None:
        """Persist the current context's cookies and storage."""
        await context.storage_state(path=self._state_path)
        print(f"[AuthManager] Auth state saved → {self._state_path}")

    def invalidate(self) -> None:
        """Delete the saved state to force a fresh login next run."""
        if os.path.exists(self._state_path):
            os.remove(self._state_path)
            print(f"[AuthManager] Auth state invalidated for env={self._env_id}")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _is_valid(state: dict) -> bool:
        """
        Check if any cookies in the state are still within their expiry.
        Returns True even if no expiry is set (assume valid).
        """
        cookies = state.get("cookies", [])
        if not cookies:
            return True  # No cookies — assume localStorage-only auth, still valid
        now = datetime.now(timezone.utc).timestamp()
        for cookie in cookies:
            expires = cookie.get("expires", -1)
            if expires == -1:
                continue  # Session cookie, no expiry
            if expires > now:
                return True  # At least one cookie is still valid
        return False
