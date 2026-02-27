"""Initialize a sample SQLite database for QueryAI demos.

This script creates `sample.db` in the same directory and populates it
using `sample_schema.sql`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "sample.db"
SCHEMA_PATH = HERE / "sample_schema.sql"


def main() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql)
        conn.commit()
        print(f"Created sample database at: {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
