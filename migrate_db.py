import sqlite3
import os
db_path = r'c:\Users\SuryaGovindhan\Documents\Automation\stest\AssureDen\assureden.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE test_steps ADD COLUMN manual_instruction TEXT')
        conn.commit()
        print('Successfully added manual_instruction column')
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print('Column manual_instruction already exists')
        else:
            print(f'SQL Error: {e}')
    finally:
        conn.close()
else:
    print('DB file not found, skipping migration')
