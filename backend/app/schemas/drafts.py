import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.schemas.object_repository import Locator


class RecordedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["NAVIGATE", "CLICK", "TYPE", "SELECT", "CHECK", "UNCHECK"]
    input_value: str = Field(default="", max_length=4096)
    locators: list[Locator] = Field(default_factory=list, max_length=10)
    is_secret: bool = False

    @model_validator(mode="after")
    def valid_target(self):
        if self.action != "NAVIGATE" and not any(x.is_active for x in self.locators):
            raise ValueError("An active locator is required")
        if self.action == "NAVIGATE" and not self.input_value:
            raise ValueError("Navigation requires a URL or variable")
        if self.action == "NAVIGATE" and len(self.input_value) > 500:
            raise ValueError("Navigation URL exceeds 500 characters")
        if self.is_secret and not re.fullmatch(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}", self.input_value):
            raise ValueError("Secret inputs must be variable placeholders")
        return self


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    steps: list[RecordedStep] = Field(min_length=1, max_length=500)


class DraftUpdate(Recording):
    expected_version: int = Field(ge=1)


class PromoteDraft(BaseModel):
    target: Literal["TEST_CASE", "FLOW", "BUSINESS_ACTION"] = "TEST_CASE"
    expected_version: int = Field(ge=1)
    page_id: UUID
