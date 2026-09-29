"""Immutable authored execution plans; secrets enter only the transient payload."""
import hashlib
import json
from copy import deepcopy
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import select

from app.core.config import settings
from app.services.variable_resolver import (
    build_env_map, resolve_value, VariableResolutionError, ValidationReport,
)

SNAPSHOT_SCHEMA_VERSION = 2
EXECUTION_PLAN_VERSION = 2


def _locator_snapshot(object_id, db, org_id):
    if not object_id:
        return None
    from app.models.object_repository import PageObject, Page, Module, Application
    obj = db.get(PageObject, object_id)
    if obj is None or obj.deleted_at is not None or obj.org_id != org_id:
        raise ValueError("Referenced page object is unavailable in this organization")
    page = db.get(Page, obj.page_id)
    module = db.get(Module, page.module_id) if page else None
    application = db.get(Application, module.application_id) if module else None
    if any(x is None or x.deleted_at is not None or x.org_id != org_id
           for x in (page, module, application)):
        raise ValueError("Referenced page object has an unavailable parent")
    locators = sorted(
        [deepcopy(x) for x in (obj.locators or []) if x.get("is_active", True)],
        key=lambda x: (not x.get("is_primary", False), x.get("priority", 1)),
    )
    if not locators:
        raise ValueError("Referenced page object has no active locators")
    primary, *fallbacks = locators
    return {
        "page_object_id": str(obj.id),
        "strategy": primary["type"], "selector": primary["value"],
        "fallbacks": [{"strategy": x["type"], "selector": x["value"]} for x in fallbacks],
    }


def _freeze_step(step, position, db, org_id):
    locator = _locator_snapshot(step.page_object_id, db, org_id)
    assertions = []
    for assertion in getattr(step, "assertions", []):
        if assertion.deleted_at is not None or not assertion.is_enabled:
            continue
        if assertion.org_id != org_id:
            raise ValueError("Assertion belongs to another organization")
        assertions.append({
            "assertion_id": str(assertion.id), "position": assertion.position,
            "assertion_type": assertion.assertion_type,
            "expected_value": assertion.expected_value or "",
            "attribute_name": assertion.attribute_name,
            "is_negated": assertion.is_negated, "is_fatal": assertion.is_fatal,
            "locator": _locator_snapshot(assertion.target_page_object_id, db, org_id) or locator,
        })
    return {
        "execution_step_id": str(uuid4()), "position": position,
        "step_id": str(step.id), "step_version": step.version, "action": step.action,
        "input_template": (step.target_url or step.input_value or "") if step.action == "NAVIGATE"
                          else (step.input_value or ""),
        "locator_snapshot": locator,
        "timeout_ms": getattr(step, "timeout_ms", 30000),
        "is_optional": getattr(step, "is_optional", False),
        "screenshot_on_failure": getattr(step, "screenshot_on_failure", True),
        "execution_hint": deepcopy(getattr(step, "execution_hint", None) or {}),
        "step_metadata": deepcopy(getattr(step, "step_metadata", None) or {}),
        "assertions": sorted(assertions, key=lambda x: x["position"]),
    }


def _resolve_tree(value, variables):
    if isinstance(value, str):
        return resolve_value(value, {}, variables, None)
    if isinstance(value, list):
        return [_resolve_tree(x, variables) for x in value]
    if isinstance(value, dict):
        return {k: _resolve_tree(v, variables) for k, v in value.items()}
    return value


def build_snapshot(*, test_case, steps, environment=None, env_variables,
                   run_variables, db):
    safe_vars = build_env_map(env_variables, include_secrets=False)
    secret_keys = [v.key for v in env_variables if v.deleted_at is None and v.is_secret]
    if set(secret_keys) & run_variables.keys():
        raise ValueError("Secret overrides are not supported; update the environment secret instead")
    # Scheduler retry policy and JSON/number datasets use JSON scalar values.
    # Keep their persisted types, but interpolate deterministic text in the plan.
    run_variables = {k: v if isinstance(v, str) else json.dumps(v, separators=(",", ":"), allow_nan=False)
                     for k, v in run_variables.items()}
    provenance = {k: "environment" for k in safe_vars}
    safe_vars.update(run_variables)
    provenance.update({k: "run_override" for k in run_variables})
    if environment and environment.base_url and "BASE_URL" not in safe_vars:
        safe_vars["BASE_URL"] = environment.base_url
        provenance["BASE_URL"] = "base_url"

    expanded, flow_versions = [], {}
    for step in steps:
        if step.action != "FLOW":
            expanded.append(_freeze_step(step, len(expanded) + 1, db, test_case.org_id))
            continue
        from app.models.flows import Flow
        from app.services.flow_revisions import get_revision
        flow = db.get(Flow, step.flow_id) if step.flow_id else None
        if flow is None or flow.deleted_at is not None or flow.org_id != test_case.org_id:
            raise ValueError("Referenced flow is unavailable in this organization")
        if any(a.deleted_at is None for a in getattr(step, "assertions", [])):
            raise ValueError("Assertions on a FLOW reference are not supported; use a separate step")
        if step.is_optional or step.timeout_ms != 30000 or any(
            getattr(step, key, None) for key in ("page_object_id", "input_value", "target_url",
                                                "execution_hint", "step_metadata")
        ) or not step.screenshot_on_failure:
            raise ValueError("Configure action settings on the flow's own steps")
        revision = get_revision(db, flow, step.flow_version)
        if not any(child["is_enabled"] for child in revision["steps"]):
            raise ValueError("Pinned flow revision has no enabled steps")
        flow_versions[f"{flow.id}:{step.flow_version}"] = {
            "version": step.flow_version, "checksum": revision["checksum"]}
        for authored in revision["steps"]:
            if not authored["is_enabled"]:
                continue
            child = SimpleNamespace(**authored)
            child.page_object_id = UUID(child.page_object_id) if child.page_object_id else None
            if child.action == "FLOW":
                raise ValueError("Nested flows are not supported")
            frozen = _freeze_step(child, len(expanded) + 1, db, test_case.org_id)
            frozen.update(from_asset_kind=revision.get("kind", "FLOW"), from_flow_id=str(flow.id), from_flow_version=step.flow_version,
                          from_flow_step_id=str(step.id))
            expanded.append(frozen)

    if len(expanded) > settings.MAX_EXPANDED_STEPS:
        raise ValueError(f"Execution plan exceeds MAX_EXPANDED_STEPS={settings.MAX_EXPANDED_STEPS}")
    errors = []
    for frozen in expanded:
        try:
            _resolve_tree(frozen, safe_vars)
            frozen["display_value"] = _resolve_tree(frozen["input_template"], safe_vars)
        except VariableResolutionError as exc:
            exc.issue.step = frozen["position"]
            exc.issue.field = "execution_step"
            errors.append(exc.issue)
            frozen["display_value"] = ""
    snapshot = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "execution_plan_version": EXECUTION_PLAN_VERSION,
        "test_case_version": test_case.version,
        "environment_id": str(environment.id) if environment else None,
        "environment_version": environment.version if environment else None,
        "flow_versions": flow_versions, "steps": expanded,
        "resolved_variables": safe_vars, "secret_variable_keys": secret_keys,
        "variable_provenance": provenance,
    }
    if len(json.dumps(snapshot, ensure_ascii=False).encode()) > settings.MAX_SNAPSHOT_BYTES:
        raise ValueError(f"Execution snapshot exceeds MAX_SNAPSHOT_BYTES={settings.MAX_SNAPSHOT_BYTES}")
    snapshot["__sha256"] = compute_snapshot_sha256(snapshot)
    return snapshot, ValidationReport(valid=not errors, errors=errors)


def compute_snapshot_sha256(snapshot):
    clean = {k: v for k, v in snapshot.items() if k != "__sha256"}
    canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_agent_payload(*, snapshot, env_variables, run_variables, environment=None,
                        protocol_version, run_id, lease_id, timeout_seconds,
                        test_case_id, test_case_version):
    if snapshot.get("snapshot_schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("This run uses an obsolete snapshot; queue a new run")
    variables = deepcopy(snapshot["resolved_variables"])
    secret_keys = snapshot["secret_variable_keys"]
    if secret_keys:
        # Until secret revisions exist, refuse silent changes while queued.
        if environment is None or environment.version != snapshot["environment_version"]:
            raise ValueError("Secret environment changed after queueing; queue a new run")
        secret_vars = [v for v in env_variables if v.key in secret_keys and v.is_secret]
        secrets = build_env_map(secret_vars, include_secrets=True)
        if set(secrets) != set(secret_keys):
            raise ValueError("An execution secret is unavailable")
        variables.update(secrets)
    resolved = _resolve_tree(snapshot["steps"], variables)
    plan = []
    for authored, step in zip(snapshot["steps"], resolved):
        step["resolved_input"] = step.pop("input_template")
        step["locator"] = step.pop("locator_snapshot")
        step["display_value"] = authored["display_value"]
        plan.append(step)
    return {
        "protocol_version": protocol_version,
        "execute_request": {
            "run_id": run_id, "lease_id": lease_id,
            "execution_plan": {"version": EXECUTION_PLAN_VERSION, "steps": plan},
            "variables": _resolve_tree(variables, variables),
            "metadata": {
                "test_case_id": test_case_id, "test_case_version": test_case_version,
                "environment_id": snapshot["environment_id"],
                "environment_version": snapshot["environment_version"],
                "timeout_seconds": timeout_seconds,
            },
        },
    }
