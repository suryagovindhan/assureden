import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import SessionLocal
from server.models import User
from server.security import get_password_hash

def seed_user():
    db = SessionLocal()
    # Check if admin exists
    admin_user = db.query(User).filter(User.username == "admin").first()
    
    if not admin_user:
        hashed_pw = get_password_hash("admin123")
        new_admin = User(
            username="admin",
            email="admin@shieldqa.local",
            role="ADMIN",
            hashed_password=hashed_pw
        )
        db.add(new_admin)
        db.commit()
        print("Admin user 'admin' created with password 'admin123'")
    else:
        print("Admin user already exists.")
        
    db.close()

if __name__ == "__main__":
    seed_user()
