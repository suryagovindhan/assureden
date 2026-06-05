"""
Seed script — creates the admin user and default built-in QA entities
Run from the AssureDen/ root:  python server/seed.py
"""
import sys, os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import SessionLocal, engine, Base
from server.models import User, Project, Environment, Variable, TestModule, TestSuite, TestCase, TestStep
from server.security import get_password_hash

# Create tables if not run via Alembic
Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()
    try:
        # 1. Admin user
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@assureden.local",
                role="ADMIN",
                hashed_password=get_password_hash("admin123"),
            )
            db.add(admin)
            print("[OK] Admin user created (admin / admin123)")

        # 2. Base Project
        proj = db.query(Project).filter(Project.name == "Demo QA Project").first()
        if not proj:
            proj = Project(name="Demo QA Project", description="Default project for AssureDen demo.")
            db.add(proj)
            db.commit() # Commit to get ID
            print("[OK] Project created: Demo QA Project")
            
            # 3. Environment
            env = Environment(project_id=proj.id, name="Staging", base_url="https://stest.securdenlabs.com")
            db.add(env)
            db.commit()
            
            # 4. Variables
            db.add(Variable(key_name="DEMO_USER", value="admin", env_id=env.id))
            print("[OK] Environment 'Staging' and variables created.")
        
        # 5. Core Test Modules
        modules = [
            dict(name="PAM Login Flow", description="Authentication tests for PAM applications."),
            dict(name="IAM Access Review", description="Access review certification flows.")
        ]
        pam_mod = None
        for m in modules:
            mod = db.query(TestModule).filter(TestModule.name == m["name"]).first()
            if not mod:
                mod = TestModule(**m)
                db.add(mod)
                print(f"[OK] Module seeded: {m['name']}")
            if m["name"] == "PAM Login Flow":
                pam_mod = mod
        db.commit()

        # 6. Sample Structured TestCase and Steps
        if pam_mod:
            tc = db.query(TestCase).filter(TestCase.name == "Valid PAM Login").first()
            if not tc:
                # Suite
                suite = TestSuite(project_id=proj.id, name="Smoke Tests", description="Critical paths.")
                db.add(suite)
                db.commit()
                
                tc = TestCase(module_id=pam_mod.id, name="Valid PAM Login", priority="HIGH")
                tc.suites.append(suite)
                db.add(tc)
                db.commit()
                
                # Resilient Steps
                step1 = TestStep(
                    test_case_id=tc.id,
                    sequence_order=1,
                    action="FILL",
                    ranked_locators=json.dumps([
                        "[data-testid='username-input']",
                        "input[name='loginId']",
                        "#user_login"
                    ]),
                    fallback_metadata=json.dumps({"label": "Username", "nearby_text": "Sign In"}),
                    input_source_type="VARIABLE",
                    input_reference="DEMO_USER"
                )
                
                step2 = TestStep(
                    test_case_id=tc.id,
                    sequence_order=2,
                    action="CLICK",
                    ranked_locators=json.dumps([
                        "[data-testid='submit-btn']",
                        "button[type='submit']",
                        ".login-submit"
                    ]),
                    expected_condition=json.dumps({"condition": "network_idle"})
                )
                
                db.add_all([step1, step2])
                print("[OK] Sample TestCase 'Valid PAM Login' with Resilient Locators created.")

        db.commit()
        print("\nSeed complete.")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
