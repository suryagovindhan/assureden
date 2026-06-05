"""
models.py — AssureDen QA-First ORM Schema
─────────────────────────────────────────
Rules:
  • Only MSSQL-safe column types: String, Integer, Float, Boolean, DateTime, Text
  • Primary keys are String(36) — UUID generated in Python, stored as string
  • M:N mappings via explicitly named association tables
  • Rich JSON-like data stored as TEXT (SQLite) / VARCHAR(MAX) (MSSQL) and parsed via properties/Pydantic
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Table, UniqueConstraint
)
from sqlalchemy.orm import relationship
from server.database import Base

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Association Tables
# ─────────────────────────────────────────────────────────────────────────────

suite_testcase_assoc = Table(
    "suite_testcase_assoc",
    Base.metadata,
    Column("suite_id",     String(36), ForeignKey("test_suites.id"), primary_key=True),
    Column("test_case_id", String(36), ForeignKey("test_cases.id"),  primary_key=True),
    Column("execution_order", Integer, default=0) # Simple ordering mechanism
)


# ─────────────────────────────────────────────────────────────────────────────
# Users & RBAC
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id              = Column(String(36),  primary_key=True, default=_uuid)
    username        = Column(String(80),  unique=True, index=True, nullable=False)
    email           = Column(String(150), unique=True, index=True, nullable=False)
    role            = Column(String(20),  nullable=False, default="TESTER")  # ADMIN | EDITOR | RUNNER | VIEWER
    hashed_password = Column(String(255), nullable=False)
    is_active       = Column(Boolean,     default=True, index=True)
    created_at      = Column(DateTime,    default=_now)
    updated_at      = Column(DateTime,    default=_now, onupdate=_now)


# ─────────────────────────────────────────────────────────────────────────────
# Core QA Domain (Projects & Environments)
# ─────────────────────────────────────────────────────────────────────────────

class Project(Base):
    """The highest RBAC boundary and logical grouping of tests."""
    __tablename__ = "projects"
    id          = Column(String(36),  primary_key=True, default=_uuid)
    name        = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text,        nullable=True)
    is_active   = Column(Boolean,     default=True, index=True)
    created_at  = Column(DateTime,    default=_now)
    updated_at  = Column(DateTime,    default=_now, onupdate=_now)
    
    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    suites       = relationship("TestSuite",   back_populates="project")
    variables    = relationship("Variable",    back_populates="project")

class Environment(Base):
    """A target instance (e.g., Staging, Prod) for a specific Project."""
    __tablename__ = "environments"
    id          = Column(String(36),  primary_key=True, default=_uuid)
    project_id  = Column(String(36),  ForeignKey("projects.id"), nullable=False, index=True)
    name        = Column(String(100), nullable=False)  # e.g., "QA-UAT"
    base_url    = Column(String(500), nullable=True)
    is_active   = Column(Boolean,     default=True)
    created_at  = Column(DateTime,    default=_now)
    updated_at  = Column(DateTime,    default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint('project_id', 'name', name='uq_env_project_name'),)

    project    = relationship("Project", back_populates="environments")
    auth_state = relationship("AuthState", back_populates="environment", uselist=False)


# ─────────────────────────────────────────────────────────────────────────────
# Data & Secret Layer
# ─────────────────────────────────────────────────────────────────────────────

class Variable(Base):
    __tablename__ = "variables"
    id          = Column(String(36), primary_key=True, default=_uuid)
    key_name    = Column(String(150), nullable=False, index=True)
    value       = Column(Text, nullable=False)
    
    # Layering Scopes (The most specific populated foreign key wins)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)
    env_id      = Column(String(36), ForeignKey("environments.id"), nullable=True)
    module_id   = Column(String(36), ForeignKey("test_modules.id"), nullable=True)
    
    is_active   = Column(Boolean, default=True)
    
    project = relationship("Project", back_populates="variables")

class Secret(Base):
    """Encrypted storage. Values are encrypted at rest using Fernet."""
    __tablename__ = "secrets"
    id          = Column(String(36), primary_key=True, default=_uuid)
    key_name    = Column(String(150), unique=True, index=True, nullable=False)
    enc_value   = Column(Text, nullable=False) # Encrypted Fernet string
    description = Column(Text, nullable=True)
    created_by  = Column(String(36), ForeignKey("users.id"))
    created_at  = Column(DateTime, default=_now)

class Dataset(Base):
    """Data-driven testing grids (e.g. CSVs conceptually)"""
    __tablename__ = "datasets"
    id          = Column(String(36), primary_key=True, default=_uuid)
    name        = Column(String(100), unique=True, nullable=False)
    data_grid   = Column(Text, nullable=True) # JSON array of dicts [ {col: val, col2: val2} ]
    created_at  = Column(DateTime, default=_now)


# ─────────────────────────────────────────────────────────────────────────────
# Support Layer (Auth & Hooks)
# ─────────────────────────────────────────────────────────────────────────────

class AuthState(Base):
    """Playwright storage_state.json payload bound to an environment."""
    __tablename__ = "auth_states"
    id             = Column(String(36), primary_key=True, default=_uuid)
    environment_id = Column(String(36), ForeignKey("environments.id"), unique=True)
    valid_until    = Column(DateTime, nullable=True)
    state_json     = Column(Text, nullable=False)
    updated_at     = Column(DateTime, default=_now, onupdate=_now)
    
    environment = relationship("Environment", back_populates="auth_state")

class Hook(Base):
    """Pre/Post conditions or generators run natively by the agent."""
    __tablename__ = "hooks"
    id          = Column(String(36), primary_key=True, default=_uuid)
    name        = Column(String(100), nullable=False)
    hook_type   = Column(String(50), nullable=False) # PRE_RUN | POST_RUN | AUTH_REFRESH
    script      = Column(Text, nullable=False)
    is_active   = Column(Boolean, default=True)


# ─────────────────────────────────────────────────────────────────────────────
# Test Definition Layer (DSL)
# ─────────────────────────────────────────────────────────────────────────────

class TestModule(Base):
    """Logical grouping of test cases (e.g., 'PAM User Rotation')."""
    __tablename__ = "test_modules"
    id          = Column(String(36),  primary_key=True, default=_uuid)
    name        = Column(String(100), unique=True, nullable=False)
    description = Column(Text,        nullable=True)
    is_active   = Column(Boolean,     default=True)
    
    test_cases  = relationship("TestCase", back_populates="module", cascade="all, delete-orphan")

class TestSuite(Base):
    """Ordered collection of TestCases to be scheduled/run together."""
    __tablename__ = "test_suites"
    id          = Column(String(36),  primary_key=True, default=_uuid)
    project_id  = Column(String(36),  ForeignKey("projects.id"), nullable=False, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True)
    
    project    = relationship("Project", back_populates="suites")
    test_cases = relationship("TestCase", secondary=suite_testcase_assoc, back_populates="suites")

class TestCase(Base):
    __tablename__ = "test_cases"
    id               = Column(String(36),  primary_key=True, default=_uuid)
    module_id        = Column(String(36),  ForeignKey("test_modules.id"), nullable=False, index=True)
    name             = Column(String(200), nullable=False)
    description      = Column(Text,        nullable=True)
    priority         = Column(String(10),  nullable=False, default="MEDIUM")  # HIGH | MEDIUM | LOW
    flaky_score      = Column(Float,       default=0.0) # Evaluated over time
    is_active        = Column(Boolean,     default=True)
    
    module     = relationship("TestModule",   back_populates="test_cases")
    suites     = relationship("TestSuite",    secondary=suite_testcase_assoc, back_populates="test_cases")
    steps      = relationship("TestStep",     back_populates="test_case", order_by="TestStep.sequence_order", cascade="all, delete-orphan")
    executions = relationship("RunExecution", back_populates="test_case")

class TestStep(Base):
    """Granular building block of a TestCase."""
    __tablename__ = "test_steps"
    id                 = Column(String(36), primary_key=True, default=_uuid)
    test_case_id       = Column(String(36), ForeignKey("test_cases.id"), nullable=False, index=True)
    sequence_order     = Column(Integer,    nullable=False)
    
    action             = Column(String(50), nullable=False) # CLICK | FILL | ASSERT_VISIBLE | NAVIGATE
    manual_instruction = Column(Text, nullable=True)        # Human-readable step instruction
    
    # Resolving Locators (Resiliency Architecture)
    ranked_locators    = Column(Text, nullable=True)  # JSON Array of dicts
    fallback_metadata  = Column(Text, nullable=True)  # JSON string of DOM context / neighbor texts
    
    # Resolving Data Input
    input_source_type  = Column(String(30), nullable=True) # FIXED | VARIABLE | DATASET | GENERATOR | SECRET
    input_reference    = Column(Text, nullable=True)       # The raw key, query, or generated strategy
    
    # Execution Rules
    expected_condition = Column(Text, nullable=True)  # JSON string {"condition": "network_idle"}
    timeout_ms         = Column(Integer, default=5000)
    retry_policy       = Column(Integer, default=1)
    
    test_case = relationship("TestCase", back_populates="steps")


# ─────────────────────────────────────────────────────────────────────────────
# Execution & Evidence Layer
# ─────────────────────────────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"
    id         = Column(String(36),  primary_key=True, default=_uuid)
    name       = Column(String(100), unique=True, index=True, nullable=False)
    status     = Column(String(20),  nullable=False, default="OFFLINE")
    host_ip    = Column(String(50),  nullable=True)
    last_seen  = Column(DateTime,    nullable=True)
    is_active  = Column(Boolean,     default=True, index=True)

    runs = relationship("RunExecution", back_populates="agent")

class RunRequest(Base):
    """The queued job payload, unresolved."""
    __tablename__ = "run_requests"
    id               = Column(String(36), primary_key=True, default=_uuid)
    suite_id         = Column(String(36), ForeignKey("test_suites.id"), nullable=True)
    test_case_id     = Column(String(36), ForeignKey("test_cases.id"), nullable=True)
    environment_id   = Column(String(36), ForeignKey("environments.id"), nullable=False)
    status           = Column(String(20), default="QUEUED") # QUEUED | RESOLVING | DISPATCHED
    created_at       = Column(DateTime, default=_now)

class RunExecution(Base):
    """A materialized run processed by the Execution Engine."""
    __tablename__ = "run_executions"
    id                  = Column(String(36), primary_key=True, default=_uuid)
    run_request_id      = Column(String(36), ForeignKey("run_requests.id"))
    test_case_id        = Column(String(36), ForeignKey("test_cases.id"), index=True)
    agent_id            = Column(String(36), ForeignKey("agents.id"), nullable=True)
    
    status              = Column(String(20), nullable=False) # SUCCESS | FAILED | FLAKY | RUNNING
    failure_classification = Column(String(50), nullable=True) # BUG | TEST_ISSUE | ENV_ISSUE | FLAKY
    failure_signature   = Column(Text, nullable=True) # Clustering hash
    
    start_time          = Column(DateTime, nullable=True)
    end_time            = Column(DateTime, nullable=True)
    total_time_ms       = Column(Integer, nullable=True)
    
    agent     = relationship("Agent", back_populates="runs")
    test_case = relationship("TestCase", back_populates="executions")
    steps     = relationship("RunStepExecution", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")

class RunStepExecution(Base):
    """Granular execution telemetry per step."""
    __tablename__ = "run_step_executions"
    id              = Column(String(36), primary_key=True, default=_uuid)
    run_id          = Column(String(36), ForeignKey("run_executions.id"), nullable=False, index=True)
    step_id         = Column(String(36), ForeignKey("test_steps.id"), nullable=False)
    
    # Telemetry
    status          = Column(String(20), nullable=False) # SUCCESS | FAILED | SKIPPED
    primary_success = Column(Boolean, default=True)      # Did ranked_locators[0] work?
    fallback_success= Column(Boolean, default=False)     # (HEALED FLAG) Did a fallback locator work?
    failed_all      = Column(Boolean, default=False)
    
    locators_attempted = Column(Text, nullable=True)     # JSON Array of which locators were tried
    successful_locator = Column(Text, nullable=True)     # The exact locator string that worked
    
    retries_used    = Column(Integer, default=0)
    execution_time_ms = Column(Integer, nullable=True)
    input_masked    = Column(Text, nullable=True)        # The resolved data used (secrets masked)
    
    error_message   = Column(Text, nullable=True)
    stack_trace     = Column(Text, nullable=True)
    
    run  = relationship("RunExecution", back_populates="steps")
    step = relationship("TestStep")
    artifacts = relationship("Artifact", back_populates="step_execution")

class Artifact(Base):
    """Structured pointer to objects in Local/S3 storage."""
    __tablename__ = "artifacts"
    id                    = Column(String(36), primary_key=True, default=_uuid)
    run_id                = Column(String(36), ForeignKey("run_executions.id"), nullable=False)
    step_execution_id     = Column(String(36), ForeignKey("run_step_executions.id"), nullable=True)
    
    artifact_type         = Column(String(50), nullable=False) # SCREENSHOT | VIDEO | TRACE | DOM_SNAPSHOT | CONSOLE_LOGS
    storage_path          = Column(String(500), nullable=False) # e.g. /server/static/artifacts/run_123/step_4.png
    created_at            = Column(DateTime, default=_now)
    
    run            = relationship("RunExecution", back_populates="artifacts")
    step_execution = relationship("RunStepExecution", back_populates="artifacts")
