"""
schemas/test_cases.py — Phase 2 Test Case Management Pydantic schemas

Enums re-exported here for use by the router.
Optimistic locking: TestCaseUpdate and TestStepUpdate include `version`.
Nested read schemas include version for safe individual updates.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.test_cases import (
    StepAction, AssertionType, SuiteStatus, TestStatus, TestPriority,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm_tags(tags: Optional[list]) -> Optional[list]:
    if tags is None:
        return None
    seen, result = set(), []
    for t in tags:
        tl = str(t).lower().strip()
        if tl and tl not in seen:
            seen.add(tl)
            result.append(tl)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TestSuite
# ─────────────────────────────────────────────────────────────────────────────

class TestSuiteCreate(BaseModel):
    name:          str                    = Field(..., min_length=1, max_length=200)
    description:   Optional[str]          = None
    status:        SuiteStatus            = SuiteStatus.ACTIVE
    tags:          Optional[list[str]]    = None
    owner_user_id: Optional[UUID]         = None
    owner_team:    Optional[str]          = Field(None, max_length=100)

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v):
        return _norm_tags(v)


class TestSuiteUpdate(BaseModel):
    name:          Optional[str]          = Field(None, min_length=1, max_length=200)
    description:   Optional[str]          = None
    status:        Optional[SuiteStatus]  = None
    tags:          Optional[list[str]]    = None
    owner_user_id: Optional[UUID]         = None
    owner_team:    Optional[str]          = Field(None, max_length=100)

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v):
        return _norm_tags(v)


class TestSuiteRead(BaseModel):
    id:            UUID
    org_id:        UUID
    name:          str
    description:   Optional[str]
    status:        str
    tags:          Optional[list[str]]
    owner_user_id: Optional[UUID]
    owner_team:    Optional[str]
    created_by:    Optional[UUID]
    created_at:    datetime
    updated_by:    Optional[UUID]
    updated_at:    datetime
    case_count:    int = 0

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# TestCase
# ─────────────────────────────────────────────────────────────────────────────

class TestCaseCreate(BaseModel):
    name:                    str                    = Field(..., min_length=1, max_length=300)
    description:             Optional[str]          = None
    suite_id:                Optional[UUID]         = None
    application_id:          Optional[UUID]         = None
    priority:                TestPriority           = TestPriority.MEDIUM
    status:                  TestStatus             = TestStatus.DRAFT
    tags:                    Optional[list[str]]    = None
    estimated_duration_secs: Optional[int]          = Field(None, ge=0)
    preconditions:           Optional[str]          = None
    postconditions:          Optional[str]          = None
    owner_user_id:           Optional[UUID]         = None
    owner_team:              Optional[str]          = Field(None, max_length=100)

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v):
        return _norm_tags(v)


class TestCaseUpdate(BaseModel):
    """
    version is required for optimistic locking.
    Server returns 409 VERSION_CONFLICT if submitted version != DB version.
    """
    version:                 int                    = Field(..., ge=1)
    name:                    Optional[str]          = Field(None, min_length=1, max_length=300)
    description:             Optional[str]          = None
    suite_id:                Optional[UUID]         = None
    application_id:          Optional[UUID]         = None
    priority:                Optional[TestPriority] = None
    status:                  Optional[TestStatus]   = None
    tags:                    Optional[list[str]]    = None
    estimated_duration_secs: Optional[int]          = Field(None, ge=0)
    preconditions:           Optional[str]          = None
    postconditions:          Optional[str]          = None
    owner_user_id:           Optional[UUID]         = None
    owner_team:              Optional[str]          = Field(None, max_length=100)

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v):
        return _norm_tags(v)


class TestCaseSummary(BaseModel):
    """Lightweight read — no steps. Used in list views."""
    id:                      UUID
    org_id:                  UUID
    suite_id:                Optional[UUID]
    application_id:          Optional[UUID]
    name:                    str
    priority:                str
    status:                  str
    version:                 int
    tags:                    Optional[list[str]]
    estimated_duration_secs: Optional[int]
    owner_user_id:           Optional[UUID]
    owner_team:              Optional[str]
    created_by:              Optional[UUID]
    created_at:              datetime
    updated_by:              Optional[UUID]
    updated_at:              datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# StepAssertion (declared before TestStep so it can be nested)
# ─────────────────────────────────────────────────────────────────────────────

class StepAssertionCreate(BaseModel):
    assertion_type:          AssertionType
    target_page_object_id:   Optional[UUID]    = None
    expected_value:          Optional[str]     = None
    attribute_name:          Optional[str]     = Field(None, max_length=100)
    is_negated:              bool              = False
    is_fatal:                bool              = True
    is_enabled:              bool              = True


class StepAssertionUpdate(BaseModel):
    assertion_type:          Optional[AssertionType] = None
    target_page_object_id:   Optional[UUID]           = None
    expected_value:          Optional[str]            = None
    attribute_name:          Optional[str]            = Field(None, max_length=100)
    is_negated:              Optional[bool]           = None
    is_fatal:                Optional[bool]           = None
    is_enabled:              Optional[bool]           = None


class StepAssertionRead(BaseModel):
    id:                      UUID
    org_id:                  UUID
    step_id:                 UUID
    position:                int
    assertion_type:          str
    target_page_object_id:   Optional[UUID]
    expected_value:          Optional[str]
    attribute_name:          Optional[str]
    is_negated:              bool
    is_fatal:                bool
    is_enabled:              bool
    created_by:              Optional[UUID]
    created_at:              datetime
    updated_by:              Optional[UUID]
    updated_at:              datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# TestStep
# ─────────────────────────────────────────────────────────────────────────────

class TestStepCreate(BaseModel):
    action:                  StepAction
    page_object_id:          Optional[UUID]    = None
    input_value:             Optional[str]     = None
    target_url:              Optional[str]     = Field(None, max_length=500)
    description:             Optional[str]     = None
    is_optional:             bool              = False
    is_enabled:              bool              = True
    timeout_ms:              int               = Field(30000, ge=100)
    screenshot_on_failure:   bool              = True
    execution_hint:          Optional[dict]    = None
    step_metadata:           Optional[dict]    = None


class TestStepUpdate(BaseModel):
    """version is NOT required for steps — only TestCase uses optimistic locking."""
    action:                  Optional[StepAction]   = None
    page_object_id:          Optional[UUID]         = None
    input_value:             Optional[str]          = None
    target_url:              Optional[str]          = Field(None, max_length=500)
    description:             Optional[str]          = None
    is_optional:             Optional[bool]         = None
    is_enabled:              Optional[bool]         = None
    timeout_ms:              Optional[int]          = Field(None, ge=100)
    screenshot_on_failure:   Optional[bool]         = None
    execution_hint:          Optional[dict]         = None
    step_metadata:           Optional[dict]         = None


class TestStepRead(BaseModel):
    id:                      UUID
    org_id:                  UUID
    test_case_id:            UUID
    position:                int
    action:                  str
    version:                 int
    page_object_id:          Optional[UUID]
    input_value:             Optional[str]
    target_url:              Optional[str]
    description:             Optional[str]
    is_optional:             bool
    is_enabled:              bool
    timeout_ms:              int
    screenshot_on_failure:   bool
    execution_hint:          Optional[dict]
    step_metadata:           Optional[dict]
    assertions:              list[StepAssertionRead] = []
    created_by:              Optional[UUID]
    created_at:              datetime
    updated_by:              Optional[UUID]
    updated_at:              datetime

    model_config = {"from_attributes": True}


class TestCaseRead(BaseModel):
    """Full document — includes nested steps and their assertions."""
    id:                      UUID
    org_id:                  UUID
    suite_id:                Optional[UUID]
    application_id:          Optional[UUID]
    name:                    str
    description:             Optional[str]
    priority:                str
    status:                  str
    version:                 int
    tags:                    Optional[list[str]]
    estimated_duration_secs: Optional[int]
    preconditions:           Optional[str]
    postconditions:          Optional[str]
    owner_user_id:           Optional[UUID]
    owner_team:              Optional[str]
    steps:                   list[TestStepRead] = []
    created_by:              Optional[UUID]
    created_at:              datetime
    updated_by:              Optional[UUID]
    updated_at:              datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Reorder
# ─────────────────────────────────────────────────────────────────────────────

class StepReorderRequest(BaseModel):
    """
    Ordered list of ALL live step IDs for this test case.
    Validation in repository: same case, no duplicates, no missing IDs.
    """
    step_ids: list[UUID] = Field(..., min_length=1)
