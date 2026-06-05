"""
bin_src/changedatabase.py — AssureDen Dialect Switch Utility
──────────────────────────────────────────────────────────────
Updates the DATABASE_URL in server/database.py to switch dialects.
Currently supports: sqlite, mssql

Usage:
  python bin_src/changedatabase.py --dialect mssql \
      --host db.company.local --port 1433 \
      --name assureden_prod --user sa --password "P@ssw0rd"

  python bin_src/changedatabase.py --dialect sqlite
"""
import argparse
import os
import re
import sys

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "database.py")

TEMPLATES = {
    "sqlite": 'DATABASE_URL = "sqlite:///{_DB_PATH}"',
    "mssql":  'DATABASE_URL = "mssql+pyodbc://{user}:{password}@{host}:{port}/{name}?driver=ODBC+Driver+17+for+SQL+Server"',
}

def switch(dialect: str, **kwargs):
    if not os.path.exists(DB_FILE):
        print(f"[ERROR] database.py not found at: {DB_FILE}")
        sys.exit(1)

    if dialect not in TEMPLATES:
        print(f"[ERROR] Unsupported dialect: {dialect}. Choose: {', '.join(TEMPLATES)}")
        sys.exit(1)

    new_url_line = TEMPLATES[dialect].format(**kwargs)

    with open(DB_FILE, "r") as f:
        content = f.read()

    updated = re.sub(r'^DATABASE_URL\s*=.*$', new_url_line, content, flags=re.MULTILINE)
    with open(DB_FILE, "w") as f:
        f.write(updated)

    print(f"[OK] database.py updated to use: {dialect}")
    print(f"[OK] New URL line: {new_url_line}")
    if dialect == "mssql":
        print("[INFO] Make sure pyodbc and 'ODBC Driver 17 for SQL Server' are installed.")
        print("[INFO] Run: python -m alembic upgrade head  — to apply schema to the new DB.")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Switch AssureDen database dialect.")
    p.add_argument("--dialect", required=True, choices=["sqlite", "mssql"])
    p.add_argument("--host",     default="localhost")
    p.add_argument("--port",     default="1433")
    p.add_argument("--name",     default="assureden")
    p.add_argument("--user",     default="sa")
    p.add_argument("--password", default="")
    args = p.parse_args()
    switch(args.dialect, **vars(args))
