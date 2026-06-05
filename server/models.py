from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, JSON, Uuid
import uuid
from datetime import datetime, timezone
from server.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    role = Column(String(20), default="TESTER") # ADMIN, TESTER
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(20), default="OFFLINE") # ONLINE, IDLE, RUNNING, OFFLINE
    host_info = Column(JSON, nullable=True) # OS, specs, IP address
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

class TestReport(Base):
    __tablename__ = "test_reports"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(Uuid, ForeignKey("agents.id"), nullable=True)
    initiated_by = Column(Uuid, ForeignKey("users.id"), nullable=True)
    test_module = Column(String(50), nullable=False) # PAM, IAM
    action = Column(String(100), nullable=False) # e.g., test_vaulting
    status = Column(String(20), nullable=False) # SUCCESS, FAILED, ERROR
    log_data = Column(JSON, nullable=True) # execution stack, steps
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

class Application(Base):
    __tablename__ = "applications"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, index=True, nullable=False)
    app_type = Column(String(50), nullable=False)   # PAM, IAM, HYBRID
    vendor = Column(String(100), nullable=True)
    base_url = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class TestModule(Base):
    __tablename__ = "test_modules"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    domain = Column(String(20), nullable=False)          # PAM | IAM
    name = Column(String(100), unique=True, nullable=False)
    action_key = Column(String(100), unique=True, nullable=False)  # e.g. test-vaulting
    description = Column(String(500), nullable=True)
    url_path = Column(String(200), nullable=True)         # frontend route
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
