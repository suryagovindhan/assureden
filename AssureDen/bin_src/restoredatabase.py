"""
bin_src/restoredatabase.py — AssureDen DB Restore Utility
──────────────────────────────────────────────────────────
Restores the AssureDen SQLite database from a backup file.
Usage:  python bin_src/restoredatabase.py --backup path/to/backup.db
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

def get_db_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assureden.db")

def restore(backup_path: str):
    db_path = get_db_path()
    if not os.path.exists(backup_path):
        print(f"[ERROR] Backup file not found: {backup_path}")
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if os.path.exists(db_path):
        save_path = db_path + f".pre_restore_{ts}"
        shutil.copy2(db_path, save_path)
        print(f"[INFO]  Current DB saved to: {save_path}")

    shutil.copy2(backup_path, db_path)
    print(f"[OK]    Database restored from: {backup_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore AssureDen database from backup.")
    parser.add_argument("--backup", required=True, help="Path to the .db backup file")
    args = parser.parse_args()
    restore(args.backup)
