
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "minicloud.db"

connection = sqlite3.connect(DB_PATH)

try:
    user = connection.execute(
        "SELECT id FROM user ORDER BY id LIMIT 1"
    ).fetchone()

    if not user:
        print("No user account found. Nothing changed.")
    else:
        files = [p for p in UPLOAD_DIR.iterdir() if p.is_file()]

        if not files:
            print("No uploaded files found. Nothing changed.")
        else:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(stored_file)"
                ).fetchall()
            }

            if "size_bytes" not in columns:
                print("The size_bytes column is missing. Nothing changed.")
            else:
                for path in files:
                    exists = connection.execute(
                        "SELECT id FROM stored_file WHERE stored_name = ?",
                        (path.name,)
                    ).fetchone()

                    if exists:
                        print(f"Already registered: {path.name}")
                        continue

                    connection.execute(
                        """
                        INSERT INTO stored_file
                            (user_id, stored_name, original_name, size_bytes)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            user[0],
                            path.name,
                            "Recovered-file" + path.suffix,
                            path.stat().st_size
                        )
                    )
                    print(f"Registered: {path.name}")

                connection.commit()
                print("Recovery complete. Your uploaded files were preserved.")
finally:
    connection.close()
