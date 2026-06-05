"""
scripts/seed_admin.py — Creates the first Organization + Admin user

Usage (from backend/ directory):
    python scripts/seed_admin.py

Only run once on a fresh database.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.repositories.foundation import OrganizationRepository, UserRepository
from app.core.security import hash_password


def seed():
    db = SessionLocal()
    try:
        org_repo  = OrganizationRepository(db)
        user_repo = UserRepository(db)

        # ── Organization ───────────────────────────────────────
        slug = "default"
        org = org_repo.get_by_slug(slug)
        if org is None:
            org = org_repo.create_org(name="Default Organization", slug=slug)
            db.commit()
            db.refresh(org)
            print(f"[OK] Organization created: {org.name} (slug={org.slug})")
        else:
            print(f"  Organization already exists: {org.slug}")

        # ── Admin User ─────────────────────────────────────────
        email = "admin@assureden.com"
        user = user_repo.get_by_email(email, org.id)
        if user is None:
            user = user_repo.create_user(
                org_id=org.id,
                username="admin",
                email=email,
                hashed_password=hash_password("Admin@1234"),
                role="ADMIN",
            )
            db.commit()
            db.refresh(user)
            print(f"[OK] Admin user created: {user.email}")
            print(f"  Login: email={email}, password=Admin@1234, org_slug={slug}")
        else:
            print(f"  Admin user already exists: {user.email}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
