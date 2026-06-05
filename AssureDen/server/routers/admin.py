"""
Admin router — /api/admin
Full CRUD for: Users, Projects, Environments, Variables, Secrets,
               TestModules, TestSuites, TestCases (with structured steps)
All endpoints require authentication.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from server.database import get_db
from server.models import User, Project, Environment, Variable, Secret, TestModule, TestSuite, TestCase, TestStep
from server.security import get_password_hash
from server.routers.auth import get_current_user
from server.core.secrets import get_secret_provider

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _auth(current_user: User = Depends(get_current_user)):
    return current_user

def _ts(dt):
    return dt.isoformat() if dt else None


# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    username: str; email: str; role: str = "TESTER"; password: str

class UserPatch(BaseModel):
    email: Optional[str] = None; role: Optional[str] = None; is_active: Optional[bool] = None

@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(_auth)):
    return [{"id": u.id, "username": u.username, "email": u.email,
             "role": u.role, "is_active": u.is_active, "created_at": _ts(u.created_at)}
            for u in db.query(User).order_by(User.username).all()]

@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    if db.query(User).filter((User.username == body.username) | (User.email == body.email)).first():
        raise HTTPException(400, "Username or email already exists.")
    u = User(username=body.username, email=body.email, role=body.role,
             hashed_password=get_password_hash(body.password))
    db.add(u); db.commit(); db.refresh(u)
    return {"id": u.id, "username": u.username}

@router.patch("/users/{uid}")
def patch_user(uid: str, body: UserPatch, db: Session = Depends(get_db), _=Depends(_auth)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404, "User not found.")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(u, k, v)
    db.commit(); return {"status": "updated"}

@router.delete("/users/{uid}", status_code=204)
def delete_user(uid: str, db: Session = Depends(get_db), me: User = Depends(_auth)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404, "User not found.")
    if u.id == me.id: raise HTTPException(400, "Cannot delete yourself.")
    db.delete(u); db.commit()


# ═══════════════════════════════════════════════════════════
#  PROJECTS
# ═══════════════════════════════════════════════════════════

class ProjectCreate(BaseModel):
    name: str; description: Optional[str] = None

class ProjectPatch(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; is_active: Optional[bool] = None

@router.get("/projects")
def list_projects(db: Session = Depends(get_db), _=Depends(_auth)):
    return [{"id": p.id, "name": p.name, "description": p.description,
             "is_active": p.is_active, "created_at": _ts(p.created_at)}
            for p in db.query(Project).order_by(Project.name).all()]

@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    if db.query(Project).filter(Project.name == body.name).first():
        raise HTTPException(400, "Project name already exists.")
    p = Project(**body.model_dump()); db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "name": p.name}

@router.patch("/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch, db: Session = Depends(get_db), _=Depends(_auth)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p: raise HTTPException(404, "Project not found.")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(p, k, v)
    db.commit(); return {"status": "updated"}

@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p: raise HTTPException(404, "Project not found.")
    db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════
#  ENVIRONMENTS
# ═══════════════════════════════════════════════════════════

class EnvCreate(BaseModel):
    project_id: str; name: str; base_url: Optional[str] = None

class EnvPatch(BaseModel):
    name: Optional[str] = None; base_url: Optional[str] = None; is_active: Optional[bool] = None

@router.get("/environments")
def list_envs(project_id: Optional[str] = None, db: Session = Depends(get_db), _=Depends(_auth)):
    q = db.query(Environment)
    if project_id: q = q.filter(Environment.project_id == project_id)
    return [{"id": e.id, "project_id": e.project_id, "name": e.name,
             "base_url": e.base_url, "is_active": e.is_active}
            for e in q.order_by(Environment.name).all()]

@router.post("/environments", status_code=201)
def create_env(body: EnvCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    e = Environment(**body.model_dump()); db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "name": e.name}

@router.patch("/environments/{eid}")
def patch_env(eid: str, body: EnvPatch, db: Session = Depends(get_db), _=Depends(_auth)):
    e = db.query(Environment).filter(Environment.id == eid).first()
    if not e: raise HTTPException(404, "Environment not found.")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(e, k, v)
    db.commit(); return {"status": "updated"}

@router.delete("/environments/{eid}", status_code=204)
def delete_env(eid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    e = db.query(Environment).filter(Environment.id == eid).first()
    if not e: raise HTTPException(404, "Environment not found.")
    db.delete(e); db.commit()


# ═══════════════════════════════════════════════════════════
#  VARIABLES
# ═══════════════════════════════════════════════════════════

class VarCreate(BaseModel):
    key_name: str; value: str
    project_id: Optional[str] = None; env_id: Optional[str] = None; module_id: Optional[str] = None

@router.get("/variables")
def list_vars(project_id: Optional[str] = None, env_id: Optional[str] = None,
              db: Session = Depends(get_db), _=Depends(_auth)):
    q = db.query(Variable)
    if project_id: q = q.filter(Variable.project_id == project_id)
    if env_id: q = q.filter(Variable.env_id == env_id)
    return [{"id": v.id, "key_name": v.key_name, "value": v.value,
             "project_id": v.project_id, "env_id": v.env_id, "module_id": v.module_id}
            for v in q.all()]

@router.post("/variables", status_code=201)
def create_var(body: VarCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    v = Variable(**body.model_dump()); db.add(v); db.commit(); db.refresh(v)
    return {"id": v.id, "key_name": v.key_name}

@router.delete("/variables/{vid}", status_code=204)
def delete_var(vid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    v = db.query(Variable).filter(Variable.id == vid).first()
    if not v: raise HTTPException(404, "Variable not found.")
    db.delete(v); db.commit()


# ═══════════════════════════════════════════════════════════
#  SECRETS  (values encrypted at rest)
# ═══════════════════════════════════════════════════════════

class SecretCreate(BaseModel):
    key_name: str; plaintext_value: str; description: Optional[str] = None

@router.get("/secrets")
def list_secrets(db: Session = Depends(get_db), me: User = Depends(_auth)):
    return [{"id": s.id, "key_name": s.key_name, "description": s.description,
             "created_at": _ts(s.created_at)}
            for s in db.query(Secret).order_by(Secret.key_name).all()]

@router.post("/secrets", status_code=201)
def create_secret(body: SecretCreate, db: Session = Depends(get_db), me: User = Depends(_auth)):
    if db.query(Secret).filter(Secret.key_name == body.key_name).first():
        raise HTTPException(400, "Secret key already exists.")
    provider = get_secret_provider()
    enc = provider.encrypt(body.plaintext_value)
    s = Secret(key_name=body.key_name, enc_value=enc,
               description=body.description, created_by=me.id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "key_name": s.key_name}

@router.delete("/secrets/{sid}", status_code=204)
def delete_secret(sid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    s = db.query(Secret).filter(Secret.id == sid).first()
    if not s: raise HTTPException(404, "Secret not found.")
    db.delete(s); db.commit()


# ═══════════════════════════════════════════════════════════
#  TEST MODULES
# ═══════════════════════════════════════════════════════════

class ModuleCreate(BaseModel):
    name: str; description: Optional[str] = None

class ModulePatch(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; is_active: Optional[bool] = None

@router.get("/modules")
def list_modules(db: Session = Depends(get_db), _=Depends(_auth)):
    return [{"id": m.id, "name": m.name, "description": m.description, "is_active": m.is_active}
            for m in db.query(TestModule).order_by(TestModule.name).all()]

@router.post("/modules", status_code=201)
def create_module(body: ModuleCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    m = TestModule(**body.model_dump()); db.add(m); db.commit(); db.refresh(m)
    return {"id": m.id, "name": m.name}

@router.patch("/modules/{mid}")
def patch_module(mid: str, body: ModulePatch, db: Session = Depends(get_db), _=Depends(_auth)):
    m = db.query(TestModule).filter(TestModule.id == mid).first()
    if not m: raise HTTPException(404, "Module not found.")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(m, k, v)
    db.commit(); return {"status": "updated"}

@router.delete("/modules/{mid}", status_code=204)
def delete_module(mid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    m = db.query(TestModule).filter(TestModule.id == mid).first()
    if not m: raise HTTPException(404, "Module not found.")
    db.delete(m); db.commit()


# ═══════════════════════════════════════════════════════════
#  TEST SUITES
# ═══════════════════════════════════════════════════════════

class SuiteCreate(BaseModel):
    project_id: str; name: str; description: Optional[str] = None

@router.get("/suites")
def list_suites(project_id: Optional[str] = None, db: Session = Depends(get_db), _=Depends(_auth)):
    q = db.query(TestSuite)
    if project_id: q = q.filter(TestSuite.project_id == project_id)
    return [{"id": s.id, "project_id": s.project_id, "name": s.name,
             "description": s.description, "is_active": s.is_active}
            for s in q.all()]

@router.post("/suites", status_code=201)
def create_suite(body: SuiteCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    s = TestSuite(**body.model_dump()); db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name}


# ═══════════════════════════════════════════════════════════
#  TEST CASES + STRUCTURED STEPS
# ═══════════════════════════════════════════════════════════

class StepIn(BaseModel):
    sequence_order: int; action: str
    manual_instruction: Optional[str] = None
    ranked_locators: Optional[List[str]] = None
    fallback_metadata: Optional[dict] = None
    input_source_type: Optional[str] = None
    input_reference: Optional[str] = None
    expected_condition: Optional[dict] = None
    timeout_ms: int = 5000; retry_policy: int = 1

class CaseCreate(BaseModel):
    module_id: str; name: str; description: Optional[str] = None
    priority: str = "MEDIUM"; steps: Optional[List[StepIn]] = None

class CasePatch(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None
    priority: Optional[str] = None; is_active: Optional[bool] = None

@router.get("/cases")
def list_cases(module_id: Optional[str] = None, db: Session = Depends(get_db), _=Depends(_auth)):
    q = db.query(TestCase)
    if module_id: q = q.filter(TestCase.module_id == module_id)
    return [{"id": c.id, "module_id": c.module_id, "name": c.name, "priority": c.priority,
             "step_count": len(c.steps), "flaky_score": c.flaky_score,
             "description": c.description, "is_active": c.is_active}
            for c in q.order_by(TestCase.priority, TestCase.name).all()]

@router.get("/cases/{cid}")
def get_case(cid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    c = db.query(TestCase).filter(TestCase.id == cid).first()
    if not c: raise HTTPException(404, "Test case not found.")
    return {
        "id": c.id, "module_id": c.module_id, "name": c.name,
        "priority": c.priority, "description": c.description,
        "steps": [
            {"id": s.id, "sequence_order": s.sequence_order, "action": s.action,
             "manual_instruction": s.manual_instruction,
             "ranked_locators": json.loads(s.ranked_locators) if s.ranked_locators else [],
             "fallback_metadata": json.loads(s.fallback_metadata) if s.fallback_metadata else {},
             "input_source_type": s.input_source_type, "input_reference": s.input_reference,
             "expected_condition": json.loads(s.expected_condition) if s.expected_condition else {},
             "timeout_ms": s.timeout_ms, "retry_policy": s.retry_policy}
            for s in c.steps
        ]
    }

@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, db: Session = Depends(get_db), _=Depends(_auth)):
    if not db.query(TestModule).filter(TestModule.id == body.module_id).first():
        raise HTTPException(404, "Module not found.")
    c = TestCase(module_id=body.module_id, name=body.name,
                 description=body.description, priority=body.priority)
    db.add(c); db.flush()  # get ID before adding steps
    if body.steps:
        for step_in in body.steps:
            step = TestStep(
                test_case_id=c.id,
                sequence_order=step_in.sequence_order,
                action=step_in.action,
                manual_instruction=step_in.manual_instruction,
                ranked_locators=json.dumps(step_in.ranked_locators) if step_in.ranked_locators else None,
                fallback_metadata=json.dumps(step_in.fallback_metadata) if step_in.fallback_metadata else None,
                input_source_type=step_in.input_source_type,
                input_reference=step_in.input_reference,
                expected_condition=json.dumps(step_in.expected_condition) if step_in.expected_condition else None,
                timeout_ms=step_in.timeout_ms,
                retry_policy=step_in.retry_policy,
            )
            db.add(step)
    db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name, "step_count": len(c.steps)}

@router.patch("/cases/{cid}")
def patch_case(cid: str, body: CasePatch, db: Session = Depends(get_db), _=Depends(_auth)):
    c = db.query(TestCase).filter(TestCase.id == cid).first()
    if not c: raise HTTPException(404, "Test case not found.")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(c, k, v)
    db.commit(); return {"status": "updated"}

@router.delete("/cases/{cid}", status_code=204)
def delete_case(cid: str, db: Session = Depends(get_db), _=Depends(_auth)):
    c = db.query(TestCase).filter(TestCase.id == cid).first()
    if not c: raise HTTPException(404, "Test case not found.")
    db.delete(c); db.commit()
