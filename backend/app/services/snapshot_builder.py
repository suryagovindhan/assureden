"""
services/snapshot_builder.py — Phase 3: Immutable execution snapshot construction.

The snapshot is the single source of truth for execution reproducibility.
Secrets are NEVER stored in the snapshot; they appear only in the transient
agent poll-response payload.

Snapshot structure (snapshot_schema_version=1):
  {
    "snapshot_schema_version": 1,
    "execution_plan_version": 1,
    "test_case_version": N,
    "environment_id": "uuid" | null,
    "environment_version": N | null,   (informational)
    "flow_versions": {"flow-uuid": {"version": N, "checksum": "hex"}},
    "steps": [
      {
        "execution_step_id": "uuid",   (generated here; identifies expanded instance)
        "position": N,                  (flattened 1-based index)
        "step_id": "uuid",             (authored step identity)
        "step_version": N,
        "action": "CLICK",
        "display_value": "...",         (input_value with secrets = ****)
        "locator_snapshot": {...} | null
      }
    ],
    "resolved_variables": {"KEY": "value"},  (non-secret only)
    "secret_variable_keys": ["PASSWORD"],
    "variable_provenance": {"KEY": "environment"|"run_override"|"base_url"}
  }

Size limits: MAX_EXPANDED_STEPS and MAX_SNAPSHOT_BYTES (from settings).
"""

import hashlib
import json
import uuid as _uuid_module
from typing import Optional, Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.variable_resolver import (
    build_env_map, validate_step_variables, ValidationReport, ValidationIssue,
)

SNAPSHOT_SCHEMA_VERSION = 1
EXECUTION_PLAN_VERSION = 1


def _uuid4() -> str:
    return str(_uuid_module.uuid4())


def _locator_snapshot(page_object, db: Session) -> Optional[dict]:
    """
    Freeze the current locator state for a PageObject.
    Returns None if page_object is None or deleted.
    """
    if page_object is None:
        return None
    # Import here to avoid circular imports
    from app.models.object_repository import Page, Module, Application
    page = db.get(Page, page_object.page_id)
    module = db.get(Module, page.module_id) if page else None
    app = db.get(Application, module.application_id) if module else None

    return {
        "page_object_id":      str(page_object.id),
        "page_object_version": getattr(page_object, "version", 1),
        "page_version":        getattr(page, "version", 1) if page else None,
        "module_version":      getattr(module, "version", 1) if module else None,
        "application_version": getattr(app, "version", 1) if app else None,
        "strategy":            page_object.locator_type,
        "selector":            page_object.selector,
        "fallbacks":           [],   # future: alternative locators
    }


def _expand_flow_steps(
    flow_id: str,
    flow_version: int,
    db: Session,
    base_position: int,
    flow_versions: dict,
    org_id,
) -> tuple[list[dict], int]:
    """
    Expand a FLOW reference into its ordered FlowStep records.
    Returns (expanded_step_dicts, next_position).
    """
    from app.models.flows import Flow, FlowStep
    from sqlalchemy import select

    flow = db.get(Flow, flow_id)
    if flow is None or flow.deleted_at is not None:
        raise ValueError(f"Flow {flow_id} not found")

    # Record this flow's version + checksum
    flow_versions[str(flow_id)] = {
        "version": flow_version,
        "checksum": flow.checksum,
    }

    steps_q = (
        select(FlowStep)
        .where(
            FlowStep.flow_id == flow.id,
            FlowStep.deleted_at.is_(None),
            FlowStep.is_enabled.is_(True),
        )
        .order_by(FlowStep.position)
    )
    flow_steps = list(db.scalars(steps_q).all())

    expanded: list[dict] = []
    pos = base_position
    for fs in flow_steps:
        po = db.get(__import__("app.models.object_repository", fromlist=["PageObject"]).PageObject, fs.page_object_id) if fs.page_object_id else None
        expanded.append({
            "execution_step_id": _uuid4(),
            "position":          pos,
            "step_id":           str(fs.id),
            "step_version":      fs.version,
            "action":            fs.action,
            "display_value":     fs.input_value or "",
            "locator_snapshot":  _locator_snapshot(po, db),
            "from_flow_id":      str(flow_id),
            "from_flow_version": flow_version,
        })
        pos += 1
    return expanded, pos


def build_snapshot(
    *,
    test_case,
    steps: list,           # live TestStep ORM objects (enabled, non-deleted)
    environment=None,      # Environment ORM object or None
    env_variables: list,   # EnvironmentVariable ORM objects
    run_variables: dict,   # run-level overrides (plaintext)
    db: Session,
) -> tuple[dict, ValidationReport]:
    """
    Build the immutable execution snapshot for a test run.

    Returns:
        (snapshot_dict, validation_report)

    Raises:
        ValueError if size limits are exceeded.
    """
    # ── Variable maps ───────────────────────────────────────────
    env_plain_all  = build_env_map(env_variables, include_secrets=True)   # for agent payload
    env_plain_safe = build_env_map(env_variables, include_secrets=False)  # for snapshot

    base_url = getattr(environment, "base_url", None)
    env_id   = str(environment.id) if environment else None
    env_ver  = getattr(environment, "version", None)

    # Determine provenance
    variable_provenance: dict[str, str] = {}
    resolved_vars_safe: dict[str, str] = {}
    secret_keys: list[str] = []

    for var in env_variables:
        if var.deleted_at is not None:
            continue
        if var.key in run_variables:
            variable_provenance[var.key] = "run_override"
        else:
            variable_provenance[var.key] = "environment"
        if var.is_secret:
            secret_keys.append(var.key)
            resolved_vars_safe[var.key] = "****"
        else:
            resolved_vars_safe[var.key] = env_plain_safe.get(var.key, "")

    for k in run_variables:
        if k not in variable_provenance:
            variable_provenance[k] = "run_override"
        if k not in resolved_vars_safe:
            resolved_vars_safe[k] = run_variables[k]

    if base_url and "BASE_URL" not in resolved_vars_safe:
        resolved_vars_safe["BASE_URL"] = base_url
        variable_provenance["BASE_URL"] = "base_url"

    # ── Validation ──────────────────────────────────────────────
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    for idx, step in enumerate(steps, start=1):
        issues = validate_step_variables(
            step_index=idx,
            fields={"input_value": step.input_value, "target_url": step.target_url},
            run_vars=run_variables,
            env_vars_plain=env_plain_safe,
            base_url=base_url,
        )
        for issue in issues:
            if issue.severity == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

    # ── Expand steps (including FLOW references) ──────────────────
    expanded_steps: list[dict] = []
    flow_versions: dict = {}
    pos = 1

    for step in steps:
        if step.action == "FLOW":
            if not step.flow_id or not step.flow_version:
                errors.append(ValidationIssue(
                    step=pos, field="flow_id", variable=None,
                    issue="MISSING", severity="error",
                    message="Step action is FLOW but no flow_id or flow_version is set",
                ))
                continue
            try:
                expanded, pos = _expand_flow_steps(
                    str(step.flow_id), step.flow_version, db, pos, flow_versions, test_case.org_id,
                )
                expanded_steps.extend(expanded)
            except ValueError as exc:
                errors.append(ValidationIssue(
                    step=pos, field="flow_id", variable=None,
                    issue="FLOW_VERSION_NOT_FOUND", severity="error",
                    message=str(exc),
                ))
        else:
            po = None
            if step.page_object_id:
                from app.models.object_repository import PageObject
                po = db.get(PageObject, step.page_object_id)
                if po is not None and po.deleted_at is not None:
                    po = None

            # Warn on deleted/missing page object
            if step.page_object_id and po is None:
                warnings.append(ValidationIssue(
                    step=pos, field="page_object_id", variable=None,
                    issue="DEPRECATED_LOCATOR", severity="warning",
                    message=f"Page object for step {pos} is deleted or not found",
                ))

            expanded_steps.append({
                "execution_step_id": _uuid4(),
                "position":          pos,
                "step_id":           str(step.id),
                "step_version":      step.version,
                "action":            step.action,
                "display_value":     step.input_value or step.target_url or "",
                "locator_snapshot":  _locator_snapshot(po, db) if po else None,
            })
            pos += 1

    # ── Size guard ───────────────────────────────────────────────
    if len(expanded_steps) > settings.MAX_EXPANDED_STEPS:
        raise ValueError(
            f"Execution plan has {len(expanded_steps)} steps, "
            f"exceeding MAX_EXPANDED_STEPS={settings.MAX_EXPANDED_STEPS}"
        )

    snapshot: dict[str, Any] = {
        "snapshot_schema_version":  SNAPSHOT_SCHEMA_VERSION,
        "execution_plan_version":   EXECUTION_PLAN_VERSION,
        "test_case_version":        test_case.version,
        "environment_id":           env_id,
        "environment_version":      env_ver,
        "flow_versions":            flow_versions,
        "steps":                    expanded_steps,
        "resolved_variables":       resolved_vars_safe,
        "secret_variable_keys":     secret_keys,
        "variable_provenance":      variable_provenance,
    }

    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(snapshot_json.encode("utf-8")) > settings.MAX_SNAPSHOT_BYTES:
        raise ValueError(
            f"Execution snapshot exceeds MAX_SNAPSHOT_BYTES={settings.MAX_SNAPSHOT_BYTES}"
        )

    sha256 = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()

    report = ValidationReport(valid=len(errors) == 0, errors=errors, warnings=warnings)
    snapshot["__sha256"] = sha256   # internal; exposed via TestRun.execution_snapshot_sha256

    return snapshot, report


def compute_snapshot_sha256(snapshot: dict) -> str:
    """Re-compute SHA-256 from snapshot dict (excluding __sha256 key)."""
    clean = {k: v for k, v in snapshot.items() if k != "__sha256"}
    canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_agent_payload(
    *,
    snapshot: dict,
    env_variables: list,   # EnvironmentVariable ORM objects (for plaintext secrets)
    run_variables: dict,
    environment=None,
    protocol_version: int,
    run_id: str,
    lease_id: str,
    timeout_seconds: int,
    test_case_id: str,
    test_case_version: int,
) -> dict:
    """
    Build the transient agent poll-response payload.
    Includes plaintext secrets — never persisted.
    """
    env_id  = str(environment.id) if environment else None
    env_ver = getattr(environment, "version", None)
    base_url = getattr(environment, "base_url", None)

    # Build fully resolved variable map (including secrets in plaintext)
    env_all = build_env_map(env_variables, include_secrets=True)
    all_vars = {}
    if base_url:
        all_vars["BASE_URL"] = base_url
    all_vars.update(env_all)
    all_vars.update(run_variables)  # run override wins

    return {
        "protocol_version": protocol_version,
        "execute_request": {
            "run_id":   run_id,
            "lease_id": lease_id,
            "execution_plan": {
                "steps": [
                    {
                        "execution_step_id": s["execution_step_id"],
                        "position":          s["position"],
                        "action":            s["action"],
                        "resolved_input":    s.get("display_value", ""),
                        "locator":           s.get("locator_snapshot"),
                        "timeout_ms":        30000,
                        "is_optional":       False,
                        "assertions":        [],
                    }
                    for s in snapshot.get("steps", [])
                ],
            },
            "variables": all_vars,
            "metadata": {
                "test_case_id":        test_case_id,
                "test_case_version":   test_case_version,
                "environment_id":      env_id,
                "environment_version": env_ver,
                "timeout_seconds":     timeout_seconds,
            },
        },
    }
