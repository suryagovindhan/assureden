"""
pom/page_factory.py — AssureDen Page Factory
─────────────────────────────────────────────
Maps {"target_app": "...", "module": "..."} to the correct
BasePage subclass. Supports case-insensitive, partial matching.

To register a new Page Object:
  1. Import the class
  2. Add an entry to _REGISTRY in the format:
     ("APP_NAME_KEYWORD", "MODULE_KEYWORD"): PageClass
"""

from __future__ import annotations
from typing import Type

from agent.pom.base_page import BasePage
from agent.pom.pam.login_page import PAMLoginPage

# ─── Registry ────────────────────────────────────────────────
# Keys are (target_app_keyword, module_keyword) — both lower-cased at match time.
# Values are the BasePage subclass to instantiate.
_REGISTRY: dict[tuple[str, str], Type[BasePage]] = {
    ("epm",     "login"):    PAMLoginPage,
    ("cyberark","login"):    PAMLoginPage,
    ("pam",     "login"):    PAMLoginPage,
    ("pam",     "vaulting"): PAMLoginPage,   # placeholder until VaultingPage is written
    # ("okta", "sso"):       OktaSSOPage,    ← example of future entry
}


class PageFactory:
    """
    Static factory.  Does NOT need to be instantiated.
    """

    @staticmethod
    def resolve(target_app: str, module: str) -> Type[BasePage] | None:
        """
        Returns the page class for the given app + module pair.
        Matching is case-insensitive and supports substring matching.
        Returns None if no match found.
        """
        app_lower = target_app.lower()
        mod_lower = module.lower()

        for (app_key, mod_key), page_class in _REGISTRY.items():
            if app_key in app_lower and mod_key in mod_lower:
                return page_class
        return None

    @staticmethod
    def list_registered() -> list[str]:
        """Returns all registered (app, module) keys as strings — useful for debugging."""
        return [f"{a} + {m}" for a, m in _REGISTRY.keys()]
