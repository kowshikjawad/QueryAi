"""Apply delivery-focused schema upgrades for QueryAI databases.

Usage:
    python -m queryai.data.migrate_delivery_schema --db-uri "postgresql+psycopg2://..."
    python -m queryai.data.migrate_delivery_schema --db-uri "postgresql+psycopg2://..." --verify --limit 10

This script applies the following changes safely (idempotent):
1) Adds columns on "Driver", "Route", and "Assignment".
2) Creates "Vehicle" and "Package" tables if missing.
3) Creates helpful indexes for query performance.
4) Backfills a few nullable metrics with 0 where useful.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from queryai.src.db_manager import DatabaseManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply delivery schema migration")
    parser.add_argument(
        "--db-uri",
        required=True,
        help="SQLAlchemy DB URI (e.g. postgresql+psycopg2://...)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Print a compact verification report after migration.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max rows to show for verification samples (default: 10).",
    )
    return parser.parse_args()


def _has_column_sqlite(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
    return any(row[1] == column_name for row in rows)


def _add_column_if_missing_sqlite(conn, table_name: str, column_name: str, col_def: str) -> None:
    if not _has_column_sqlite(conn, table_name, column_name):
        conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {col_def}'))


def apply_postgres(conn) -> None:
    conn.execute(
        text(
            '''
            ALTER TABLE "Driver"
              ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
              ADD COLUMN IF NOT EXISTS email VARCHAR(100),
              ADD COLUMN IF NOT EXISTS license_number VARCHAR(50),
              ADD COLUMN IF NOT EXISTS hire_date DATE,
              ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active',
              ADD COLUMN IF NOT EXISTS vehicle_type VARCHAR(30)
            '''
        )
    )

    conn.execute(
        text(
            '''
            ALTER TABLE "Route"
              ADD COLUMN IF NOT EXISTS zone VARCHAR(20),
              ADD COLUMN IF NOT EXISTS area_postcode VARCHAR(10),
              ADD COLUMN IF NOT EXISTS total_stops INT,
              ADD COLUMN IF NOT EXISTS estimated_duration_mins INT,
              ADD COLUMN IF NOT EXISTS date DATE
            '''
        )
    )

    conn.execute(
        text(
            '''
            ALTER TABLE "Assignment"
              ADD COLUMN IF NOT EXISTS date DATE,
              ADD COLUMN IF NOT EXISTS start_time TIME,
              ADD COLUMN IF NOT EXISTS end_time TIME,
              ADD COLUMN IF NOT EXISTS total_packages INT,
              ADD COLUMN IF NOT EXISTS delivered_packages INT,
              ADD COLUMN IF NOT EXISTS failed_deliveries INT DEFAULT 0,
              ADD COLUMN IF NOT EXISTS returned_packages INT DEFAULT 0,
              ADD COLUMN IF NOT EXISTS notes TEXT
            '''
        )
    )

    conn.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS "Vehicle" (
              id SERIAL PRIMARY KEY,
              driver_id INT REFERENCES "Driver"(id) ON DELETE SET NULL,
              plate_number VARCHAR(20) UNIQUE,
              type VARCHAR(30),
              capacity_packages INT,
              status VARCHAR(20) DEFAULT 'active'
            )
            '''
        )
    )

    conn.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS "Package" (
              id SERIAL PRIMARY KEY,
              assignment_id INT REFERENCES "Assignment"(id) ON DELETE CASCADE,
              tracking_number VARCHAR(50) UNIQUE,
              recipient_name VARCHAR(100),
              delivery_address TEXT,
              postcode VARCHAR(10),
              status VARCHAR(20) DEFAULT 'pending',
              attempted_at TIMESTAMP,
              delivered_at TIMESTAMP,
              failure_reason TEXT
            )
            '''
        )
    )

    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_route_date ON "Route"(date)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_assignment_date ON "Assignment"(date)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_assignment_id ON "Package"(assignment_id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_postcode ON "Package"(postcode)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_status ON "Package"(status)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_vehicle_driver_id ON "Vehicle"(driver_id)'))


def apply_sqlite(conn) -> None:
    _add_column_if_missing_sqlite(conn, "Driver", "phone", "TEXT")
    _add_column_if_missing_sqlite(conn, "Driver", "email", "TEXT")
    _add_column_if_missing_sqlite(conn, "Driver", "license_number", "TEXT")
    _add_column_if_missing_sqlite(conn, "Driver", "hire_date", "TEXT")
    _add_column_if_missing_sqlite(conn, "Driver", "status", "TEXT DEFAULT 'active'")
    _add_column_if_missing_sqlite(conn, "Driver", "vehicle_type", "TEXT")

    _add_column_if_missing_sqlite(conn, "Route", "zone", "TEXT")
    _add_column_if_missing_sqlite(conn, "Route", "area_postcode", "TEXT")
    _add_column_if_missing_sqlite(conn, "Route", "total_stops", "INTEGER")
    _add_column_if_missing_sqlite(conn, "Route", "estimated_duration_mins", "INTEGER")
    _add_column_if_missing_sqlite(conn, "Route", "date", "TEXT")

    _add_column_if_missing_sqlite(conn, "Assignment", "date", "TEXT")
    _add_column_if_missing_sqlite(conn, "Assignment", "start_time", "TEXT")
    _add_column_if_missing_sqlite(conn, "Assignment", "end_time", "TEXT")
    _add_column_if_missing_sqlite(conn, "Assignment", "total_packages", "INTEGER")
    _add_column_if_missing_sqlite(conn, "Assignment", "delivered_packages", "INTEGER")
    _add_column_if_missing_sqlite(conn, "Assignment", "failed_deliveries", "INTEGER DEFAULT 0")
    _add_column_if_missing_sqlite(conn, "Assignment", "returned_packages", "INTEGER DEFAULT 0")
    _add_column_if_missing_sqlite(conn, "Assignment", "notes", "TEXT")

    conn.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS "Vehicle" (
              id INTEGER PRIMARY KEY,
              driver_id INTEGER,
              plate_number TEXT UNIQUE,
              type TEXT,
              capacity_packages INTEGER,
              status TEXT DEFAULT 'active',
              FOREIGN KEY(driver_id) REFERENCES "Driver"(id)
            )
            '''
        )
    )

    conn.execute(
        text(
            '''
            CREATE TABLE IF NOT EXISTS "Package" (
              id INTEGER PRIMARY KEY,
              assignment_id INTEGER,
              tracking_number TEXT UNIQUE,
              recipient_name TEXT,
              delivery_address TEXT,
              postcode TEXT,
              status TEXT DEFAULT 'pending',
              attempted_at TEXT,
              delivered_at TEXT,
              failure_reason TEXT,
              FOREIGN KEY(assignment_id) REFERENCES "Assignment"(id)
            )
            '''
        )
    )

    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_route_date ON "Route"(date)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_assignment_date ON "Assignment"(date)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_assignment_id ON "Package"(assignment_id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_postcode ON "Package"(postcode)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_package_status ON "Package"(status)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_vehicle_driver_id ON "Vehicle"(driver_id)'))


def backfill_defaults(conn) -> None:
    conn.execute(text('UPDATE "Driver" SET status = COALESCE(status, :active)'), {"active": "active"})
    conn.execute(
        text(
            '''
            UPDATE "Assignment"
            SET
              total_packages = COALESCE(total_packages, 0),
              delivered_packages = COALESCE(delivered_packages, 0),
              failed_deliveries = COALESCE(failed_deliveries, 0),
              returned_packages = COALESCE(returned_packages, 0)
            '''
        )
    )


def verify(conn, limit: int) -> None:
    print("\nVerification summary:")
    for table in ["Driver", "Route", "Assignment", "Vehicle", "Package"]:
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
        print(f"- {table}: {count} row(s)")

    rows = conn.execute(
        text(
            '''
            SELECT "name", "status", "vehicle_type"
            FROM "Driver"
            ORDER BY "name"
            LIMIT :limit
            '''
        ),
        {"limit": max(limit, 1)},
    ).fetchall()

    if rows:
        print("\nDriver sample:")
        for row in rows:
            print(f"- {row[0]} | status={row[1]} | vehicle_type={row[2]}")


def main() -> int:
    args = parse_args()

    # Catch common copy/paste placeholder values early.
    if "user:pass@host" in args.db_uri or "@host:" in args.db_uri:
        raise SystemExit(
            "Invalid --db-uri: placeholder values detected. "
            "Use a real host/user/password, e.g. "
            "postgresql+psycopg2://myuser:mypassword@localhost:5432/mydb"
        )

    db = DatabaseManager(args.db_uri)

    try:
        with db.engine.begin() as conn:
            dialect = getattr(db.engine.dialect, "name", "")
            if dialect == "postgresql":
                apply_postgres(conn)
            elif dialect == "sqlite":
                apply_sqlite(conn)
            else:
                raise ValueError(f"Unsupported dialect for this migration helper: {dialect}")

            backfill_defaults(conn)
    except OperationalError as exc:
        raise SystemExit(
            "Database connection failed. Check --db-uri host/user/password/port/dbname, "
            "and confirm the PostgreSQL server is reachable. "
            f"Original error: {exc}"
        ) from exc

    print("✅ Delivery schema migration applied successfully.")

    if args.verify:
        with db.engine.connect() as conn:
            verify(conn, args.limit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
