"""Database connection and query execution utilities for QueryAI.

This module currently focuses on SQLite via SQLAlchemy but is structured
so it can be extended to other databases later (PostgreSQL/MySQL).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

READ_ONLY_BLOCKLIST = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE")


def build_sqlite_uri_from_path(path: str) -> str:
	"""Build a SQLAlchemy SQLite URI from a filesystem path.

	Handles both relative and absolute paths.
	"""

	path = path.strip()
	if path.lower().startswith("sqlite:"):
		return path
	# Use sqlite+pysqlite for SQLAlchemy 2.x; fallback-compatible with sqlite://
	return f"sqlite:///{path}"


def is_read_only_sql(sql: str) -> bool:
	"""Return True if the SQL appears to be read-only.

	This is a simple heuristic used as an extra guardrail. The main
	enforcement should also live in the LLM prompting and higher layers.
	"""

	normalized = " ".join(sql.strip().upper().split())
	return not any(keyword in normalized for keyword in READ_ONLY_BLOCKLIST)


@dataclass
class QueryResult:
	"""Container for a query result.

	Attributes
	----------
	dataframe:
		Pandas DataFrame with the result rows.
	rowcount:
		Number of rows returned (for SELECT) or affected.
	"""

	dataframe: pd.DataFrame
	rowcount: int


class DatabaseManager:
	"""Lightweight wrapper around SQLAlchemy for read-only queries."""

	def __init__(self, uri: str) -> None:
		self._uri = uri
		self._engine: Optional[Engine] = None

	@property
	def engine(self) -> Engine:
		if self._engine is None:
			self._engine = create_engine(self._uri, future=True)
		return self._engine

	def test_connection(self) -> bool:
		"""Return True if a simple `SELECT 1` succeeds."""

		try:
			with self.engine.connect() as conn:
				conn.execute(text("SELECT 1"))
			return True
		except SQLAlchemyError:
			return False

	def get_schema_summary(self) -> str:
		"""Return a simple human-readable schema summary for the DB.

		This will be fed into the LLM as context during Text-to-SQL.
		"""

		inspector = inspect(self.engine)
		lines: list[str] = []

		for table_name in inspector.get_table_names():
			columns = inspector.get_columns(table_name)
			col_desc = ", ".join(f"{c['name']} ({c.get('type')})" for c in columns)
			lines.append(f"Table {table_name}: {col_desc}")

		return "\n".join(lines)

	def run_read_only_query(self, sql: str, params: Optional[dict[str, Any]] = None) -> QueryResult:
		"""Execute a read-only SQL statement and return a QueryResult.

		Raises ValueError if the SQL is deemed unsafe (non-read-only).
		"""

		if not is_read_only_sql(sql):
			raise ValueError("Only read-only SELECT-style queries are allowed.")

		with self.engine.connect() as conn:
			result = conn.execute(text(sql), params or {})
			rows = result.fetchall()
			dataframe = pd.DataFrame(rows, columns=result.keys())
			return QueryResult(dataframe=dataframe, rowcount=len(rows))

