"""
server/core/data_resolver.py — Layered Variable Resolution Engine
──────────────────────────────────────────────────────────────────
Resolution Priority (most-specific wins):
  1. Run-level overrides (ad-hoc)
  2. TestCase + Environment
  3. TestCase (global)
  4. Module + Environment
  5. Module (global)
  6. Project + Environment
  7. Project (global)
  8. Global (no scope)

Built-in generators (input_source_type == "GENERATOR"):
  email, username, fullname, password, phone, numeric, uuid
"""

import uuid
import random
import string
from sqlalchemy.orm import Session
from server.models import Variable


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Generators
# ─────────────────────────────────────────────────────────────────────────────

def _generate(strategy: str) -> str:
    s = strategy.lower().strip()
    if s == "email":
        return f"qa_{_rand_str(6)}@testmail.assureden.local"
    if s == "username":
        return f"user_{_rand_str(6)}"
    if s == "fullname":
        first = random.choice(["Alex", "Jordan", "Morgan", "Casey", "Taylor"])
        last  = random.choice(["Smith", "Lee", "Chen", "Patel", "Kim"])
        return f"{first} {last}"
    if s == "password":
        chars = string.ascii_letters + string.digits + "!@#$"
        return "".join(random.choices(chars, k=12))
    if s == "phone":
        return f"+1{random.randint(2000000000, 9999999999)}"
    if s == "numeric":
        return str(random.randint(100000, 999999))
    if s == "uuid":
        return str(uuid.uuid4())
    raise ValueError(f"Unknown generator strategy: '{strategy}'")


def _rand_str(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ─────────────────────────────────────────────────────────────────────────────
# Layered Resolver
# ─────────────────────────────────────────────────────────────────────────────

class DataResolver:
    """
    Resolves input_reference strings against the layered variable store.
    Usage:
        resolver = DataResolver(db, env_id="...", module_id="...", project_id="...")
        value = resolver.resolve(input_source_type, input_reference)
    """

    def __init__(
        self,
        db: Session,
        project_id: str | None = None,
        env_id: str | None = None,
        module_id: str | None = None,
        run_overrides: dict | None = None,
    ):
        self._db = db
        self._project_id = project_id
        self._env_id = env_id
        self._module_id = module_id
        self._run_overrides = run_overrides or {}

    def resolve(self, source_type: str, reference: str) -> str:
        """
        Resolve a single step input to its concrete value.
        Returns the resolved string value.
        Raises ValueError if the key cannot be found in any scope.
        """
        t = (source_type or "FIXED").upper()

        if t == "FIXED":
            return reference

        if t == "GENERATOR":
            return _generate(reference)

        if t == "VARIABLE":
            return self._resolve_variable(reference)

        if t == "SECRET":
            # Secret resolution is deferred to the agent (never sent over wire in plaintext)
            # We return a placeholder that the agent will resolve using its own decrypt call
            return f"__SECRET__:{reference}"

        if t == "RUNTIME":
            # Runtime prompts are placeholders — the agent will prompt at execution time
            return f"__RUNTIME__:{reference}"

        raise ValueError(f"Unknown input_source_type: '{source_type}'")

    def _resolve_variable(self, key: str) -> str:
        """Walk the scope chain from most-specific to least-specific."""

        # 0. Run-level ad-hoc override (highest priority)
        if key in self._run_overrides:
            return self._run_overrides[key]

        # Build ordered scope queries (most specific first)
        candidates = []

        # Module + Env
        if self._module_id and self._env_id:
            candidates.append(
                self._db.query(Variable).filter(
                    Variable.key_name == key,
                    Variable.module_id == self._module_id,
                    Variable.env_id == self._env_id,
                ).first()
            )
        # Module only
        if self._module_id:
            candidates.append(
                self._db.query(Variable).filter(
                    Variable.key_name == key,
                    Variable.module_id == self._module_id,
                    Variable.env_id.is_(None),
                ).first()
            )
        # Project + Env
        if self._project_id and self._env_id:
            candidates.append(
                self._db.query(Variable).filter(
                    Variable.key_name == key,
                    Variable.project_id == self._project_id,
                    Variable.env_id == self._env_id,
                ).first()
            )
        # Project only
        if self._project_id:
            candidates.append(
                self._db.query(Variable).filter(
                    Variable.key_name == key,
                    Variable.project_id == self._project_id,
                    Variable.env_id.is_(None),
                ).first()
            )
        # Global (no scope)
        candidates.append(
            self._db.query(Variable).filter(
                Variable.key_name == key,
                Variable.project_id.is_(None),
                Variable.module_id.is_(None),
                Variable.env_id.is_(None),
            ).first()
        )

        for var in candidates:
            if var is not None:
                return var.value

        raise ValueError(
            f"Variable '{key}' not found in any scope "
            f"(project={self._project_id}, env={self._env_id}, module={self._module_id})."
        )
