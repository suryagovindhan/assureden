"""
services/variable_resolver.py — Phase 3 variable resolution engine.

Resolution precedence (evaluated in order, first match wins):
  1. run_variables (run-level override)
  2. Environment variable
  3. environment.base_url → {{BASE_URL}} shortcut
  4. → raise VariableResolutionError (MISSING)

Rules:
  - Variable names are CASE-SENSITIVE: BASE_URL ≠ base_url
  - Cycle detection: A={{B}}, B={{A}} → CYCLE_DETECTED
  - Recursion depth limit: configurable, default 20
  - Secrets are resolved to plaintext for the execution payload (transient)
    and to **** for the snapshot display_value
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.crypto import decrypt, is_crypto_configured


PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class ValidationIssue:
    step: Optional[int]
    field: str
    variable: Optional[str]
    issue: str   # MISSING | CYCLE_DETECTED | RECURSION_LIMIT | DEPRECATED_LOCATOR
    severity: str = "error"    # error | warning
    message: str = ""


@dataclass
class ValidationReport:
    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


class VariableResolutionError(Exception):
    """Raised during resolution; collected into ValidationReport by callers."""
    def __init__(self, issue: ValidationIssue):
        self.issue = issue
        super().__init__(issue.issue)


def _extract_placeholders(text: str) -> list[str]:
    """Return all {{VAR}} names found in text."""
    return PLACEHOLDER_RE.findall(text)


def resolve_value(
    text: str,
    run_vars: dict[str, str],
    env_vars: dict[str, str],  # plaintext (decrypted)
    base_url: Optional[str],
    *,
    depth: int = 0,
    visited: Optional[set] = None,
    max_depth: int | None = None,
) -> str:
    """
    Recursively resolve {{PLACEHOLDER}} references in text.
    Raises VariableResolutionError on cycle or missing variable.
    """
    if max_depth is None:
        max_depth = settings.VARIABLE_MAX_RECURSION_DEPTH
    if visited is None:
        visited = set()
    if depth > max_depth:
        raise VariableResolutionError(ValidationIssue(
            step=None, field="", variable=None,
            issue="RECURSION_LIMIT", severity="error",
            message=f"Variable recursion depth exceeded ({max_depth})",
        ))

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name in visited:
            raise VariableResolutionError(ValidationIssue(
                step=None, field="", variable=name,
                issue="CYCLE_DETECTED", severity="error",
                message=f"Cycle detected in variable '{name}'",
            ))
        visited_next = visited | {name}
        # Precedence: run_vars > env_vars > base_url shortcut
        if name in run_vars:
            raw = run_vars[name]
        elif name in env_vars:
            raw = env_vars[name]
        elif name == "BASE_URL" and base_url is not None:
            raw = base_url
        else:
            raise VariableResolutionError(ValidationIssue(
                step=None, field="", variable=name,
                issue="MISSING", severity="error",
                message=f"Variable '{{{{name}}}}' is not defined",
            ))
        # Recurse into the resolved value
        return resolve_value(
            raw, run_vars, env_vars, base_url,
            depth=depth + 1, visited=visited_next, max_depth=max_depth,
        )

    return PLACEHOLDER_RE.sub(_replace, text)


def build_env_map(
    variables: list,          # list of EnvironmentVariable ORM objects
    include_secrets: bool,    # True for agent payload; False for snapshot
) -> dict[str, str]:
    """
    Decrypt environment variables into a plaintext map.
    If include_secrets=False, secrets are mapped to '****'.
    """
    result: dict[str, str] = {}
    for var in variables:
        if var.deleted_at is not None:
            continue
        if var.is_secret and not include_secrets:
            result[var.key] = "****"
        else:
            if is_crypto_configured():
                result[var.key] = decrypt(var.value_encrypted, var.key_id)
            else:
                # Unencrypted fallback (test environments without keys configured)
                result[var.key] = var.value_encrypted
    return result


def validate_step_variables(
    step_index: int,
    fields: dict[str, Optional[str]],   # {field_name: field_value}
    run_vars: dict[str, str],
    env_vars_plain: dict[str, str],      # non-secret only (or **** for secrets)
    base_url: Optional[str],
) -> list[ValidationIssue]:
    """
    Check all {{VAR}} placeholders in step fields.
    Returns list of issues (errors and warnings).
    """
    issues: list[ValidationIssue] = []
    for field_name, value in fields.items():
        if not value:
            continue
        for name in _extract_placeholders(value):
            if (
                name not in run_vars
                and name not in env_vars_plain
                and not (name == "BASE_URL" and base_url is not None)
            ):
                issues.append(ValidationIssue(
                    step=step_index, field=field_name, variable=name,
                    issue="MISSING", severity="error",
                    message=f"Variable '{{{{{name}}}}}' is not defined",
                ))
    return issues
