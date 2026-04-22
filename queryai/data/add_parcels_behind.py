"""Add and backfill `parcelsBehind` column on Assignment table.

Usage:
    python -m queryai.data.add_parcels_behind --db-uri "postgresql+psycopg2://..."
	python -m queryai.data.add_parcels_behind --db-uri "postgresql+psycopg2://..." --verify --limit 10

This script:
1) Adds "parcelsBehind" INTEGER column to "Assignment" if missing.
2) Backfills existing NULL rows with random integers from 10 to 50 (inclusive).
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from queryai.src.db_manager import DatabaseManager


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Add/backfill parcelsBehind on Assignment")
	parser.add_argument(
		"--db-uri",
		required=True,
		help="SQLAlchemy DB URI (e.g. postgresql+psycopg2://...)",
	)
	parser.add_argument(
		"--verify",
		action="store_true",
		help="Print sample rows after update to verify backfill values.",
	)
	parser.add_argument(
		"--limit",
		type=int,
		default=10,
		help="Max rows to print for verification output (default: 10).",
	)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	db = DatabaseManager(args.db_uri)

	with db.engine.begin() as conn:
		dialect = getattr(db.engine.dialect, "name", "")

		if dialect == "postgresql":
			conn.execute(text('ALTER TABLE "Assignment" ADD COLUMN IF NOT EXISTS "parcelsBehind" INTEGER'))
			conn.execute(
				text(
					'UPDATE "Assignment" '
					'SET "parcelsBehind" = FLOOR(RANDOM() * 41 + 10)::int '
					'WHERE "parcelsBehind" IS NULL'
				)
			)
		elif dialect == "sqlite":
			columns = conn.execute(text("PRAGMA table_info('Assignment')")).fetchall()
			has_column = any(row[1] == "parcelsBehind" for row in columns)
			if not has_column:
				conn.execute(text('ALTER TABLE "Assignment" ADD COLUMN "parcelsBehind" INTEGER'))
			conn.execute(
				text(
					'UPDATE "Assignment" '
					'SET "parcelsBehind" = (ABS(RANDOM()) % 41) + 10 '
					'WHERE "parcelsBehind" IS NULL'
				)
			)
		else:
			raise ValueError(f"Unsupported dialect for this helper: {dialect}")

	print("✅ Added/backfilled Assignment.parcelsBehind (10-50 for existing NULL rows).")

	if args.verify:
		with db.engine.connect() as conn:
			print("\nVerification sample:")
			try:
				rows = conn.execute(
					text(
						'SELECT "Driver"."name" AS driver_name, "Assignment"."parcelsBehind" '
						'FROM "Assignment" '
						'JOIN "Driver" ON "Assignment"."driverId" = "Driver"."id" '
						'ORDER BY "Driver"."name" '
						'LIMIT :limit'
					),
					{"limit": max(args.limit, 1)},
				).fetchall()
				for row in rows:
					print(f"- {row[0]}: {row[1]}")
			except Exception:
				rows = conn.execute(
					text(
						'SELECT "parcelsBehind" '
						'FROM "Assignment" '
						'ORDER BY "parcelsBehind" '
						'LIMIT :limit'
					),
					{"limit": max(args.limit, 1)},
				).fetchall()
				for idx, row in enumerate(rows, start=1):
					print(f"- row {idx}: {row[0]}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
