"""Core Text-to-SQL orchestration logic for QueryAI (Sprint 1).

This module coordinates between the DatabaseManager and LLMEngine to
implement a simple agentic reasoning loop with self-correction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .db_manager import DatabaseManager, QueryResult
from .llm_engine import LLMEngine, UsageStats


@dataclass
class AgentResponse:
	sql: str
	result: Optional[QueryResult]
	error: Optional[str]
	attempts: int
	answer: Optional[str] = None
	usage: Optional[UsageStats] = None


class TextToSQLAgent:
	"""Simple Text-to-SQL agent with up to N self-correction attempts."""

	def __init__(
		self,
		db: DatabaseManager,
		llm_engine: LLMEngine,
		max_retries: int = 3,
	) -> None:
		self._db = db
		self._llm = llm_engine
		self._max_retries = max_retries
		self._sql_cache: dict[str, str] = {}
		self._schema_summary: Optional[str] = None
		self._dialect: Optional[str] = None

	# ── Local formatting helpers ──────────────────────────────────

	@staticmethod
	def _needs_llm_answer(result: QueryResult) -> bool:
		"""Return True if the result is complex enough to need an LLM summary."""
		df = result.dataframe
		if df.empty:
			return False
		# Single-value or single-column results can be formatted locally
		if len(df) == 1 and len(df.columns) <= 2:
			return False
		if len(df.columns) == 1:
			return False
		return True

	@staticmethod
	def _format_simple_answer(question: str, result: QueryResult) -> str:
		"""Format simple query results without calling the LLM."""
		df = result.dataframe
		if df.empty:
			return "No matching data was found."

		# Single value (e.g. COUNT, SUM)
		if len(df) == 1 and len(df.columns) == 1:
			return f"The answer is: {df.iloc[0, 0]}"

		# Single row, two columns (e.g. name + value)
		if len(df) == 1 and len(df.columns) == 2:
			cols = df.columns.tolist()
			return f"{cols[0]}: {df.iloc[0, 0]}, {cols[1]}: {df.iloc[0, 1]}"

		# Single-column list
		if len(df.columns) == 1:
			col = df.columns[0]
			values = df[col].tolist()
			if len(values) <= 30:
				items = ", ".join(str(v) for v in values)
				return f"Here are the {col} ({len(values)} result(s)): {items}"
			return f"Found {len(values)} results for {col}."

		return f"Query returned {len(df)} row(s) across {len(df.columns)} columns."

	@staticmethod
	def _results_to_text(result: QueryResult, max_rows: int = 200, max_chars: int = 12000) -> str:
		"""Convert results to a bounded text payload for LLM answer generation."""
		df = result.dataframe
		if df.empty:
			return ""

		preview = df.head(max_rows)
		text_value = preview.to_string(index=False)
		if len(text_value) > max_chars:
			text_value = text_value[:max_chars]
		return text_value

	def _get_schema_context(self) -> tuple[str, str]:
		"""Return cached schema summary and SQL dialect for prompt context."""
		if self._schema_summary is None:
			self._schema_summary = self._db.get_schema_summary()
		if self._dialect is None:
			self._dialect = getattr(self._db.engine.dialect, "name", "sqlite")
		return self._schema_summary, self._dialect

	@staticmethod
	def _quote_column_reference(sql: str, qualifier: str, column: str) -> str:
		"""Quote a dotted column reference (e.g. a.driverId -> a."driverId")."""
		pattern = re.compile(
			rf'(?<!")\b{re.escape(qualifier)}\.{re.escape(column)}\b(?!")',
			flags=re.IGNORECASE,
		)
		return pattern.sub(f'{qualifier}."{column}"', sql)

	@classmethod
	def _auto_quote_from_postgres_error(cls, sql: str, error_message: str) -> Optional[str]:
		"""Return corrected SQL using Postgres undefined-column hints when available."""
		if "UndefinedColumn" not in error_message and "does not exist" not in error_message:
			return None

		fixed_sql = sql

		# Example hint: Perhaps you meant to reference the column "a.driverId".
		for qualifier, column in re.findall(
			r'Perhaps you meant to reference the column "([^"]+)\.([^"]+)"',
			error_message,
		):
			fixed_sql = cls._quote_column_reference(fixed_sql, qualifier, column)

		# Also handle messages that mention a bare camelCase column name.
		for column in re.findall(r'column\s+"([A-Za-z_][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*)"', error_message):
			fixed_sql = re.sub(
				rf'(?<!")\b{re.escape(column)}\b(?!")',
				r'"' + column + r'"',
				fixed_sql,
			)

		return fixed_sql if fixed_sql != sql else None

	# ── Main entry point ──────────────────────────────────────────

	def run_sql(self, sql: str, question: str | None = None) -> AgentResponse:
		"""Execute user-provided SQL with the same read-only safeguards.

		This is used by the UI when users edit generated SQL manually.
		"""
		self._llm.reset_usage()
		sql = sql.strip()
		if not sql:
			return AgentResponse(
				sql="",
				result=None,
				error="SQL is empty.",
				attempts=1,
				usage=self._llm.usage,
			)

		try:
			result = self._db.run_read_only_query(sql)
			if self._needs_llm_answer(result):
				results_text = self._results_to_text(result)
				answer = self._llm.generate_answer(
					question=(question or "Summarize this SQL result"),
					sql=sql,
					results=results_text,
				)
			else:
				answer = self._format_simple_answer(question or "", result)

			return AgentResponse(
				sql=sql,
				result=result,
				error=None,
				attempts=1,
				answer=answer,
				usage=self._llm.usage,
			)
		except Exception as exc:  # noqa: BLE001 - UI-facing execution path
			return AgentResponse(
				sql=sql,
				result=None,
				error=str(exc),
				attempts=1,
				usage=self._llm.usage,
			)

	def answer_question(self, question: str) -> AgentResponse:
		self._llm.reset_usage()
		schema_summary, dialect = self._get_schema_context()

		attempts = 0
		last_error: Optional[str] = None
		sql: str = ""
		cache_key = question.strip().lower()

		# Check cache for repeated questions
		if cache_key in self._sql_cache:
			sql = self._sql_cache[cache_key]
		else:
			sql = self._llm.generate_sql(
				question=question,
				schema_summary=schema_summary,
				dialect=dialect,
			)
		attempts += 1

		while attempts <= self._max_retries:
			try:
				result = self._db.run_read_only_query(sql)

				# Cache successful SQL
				self._sql_cache[cache_key] = sql

				# Only call LLM for answer if the result is complex
				if self._needs_llm_answer(result):
					results_text = self._results_to_text(result)
					answer = self._llm.generate_answer(
						question=question,
						sql=sql,
						results=results_text,
					)
				else:
					answer = self._format_simple_answer(question, result)

				return AgentResponse(sql=sql, result=result, error=None, attempts=attempts, answer=answer, usage=self._llm.usage)
			except Exception as exc:  # noqa: BLE001 - top-level agent loop
				last_error = str(exc)

				# Deterministic Postgres fix: quote hinted mixed-case identifiers.
				if dialect == "postgresql":
					auto_fixed = self._auto_quote_from_postgres_error(sql, last_error)
					if auto_fixed is not None:
						sql = auto_fixed
						attempts += 1
						continue

				if attempts >= self._max_retries:
					break

				# Ask LLM to refine the SQL using the error message
				sql = self._llm.refine_sql_on_error(
					question=question,
					schema_summary=schema_summary,
					previous_sql=sql,
					error_message=last_error,
					dialect=dialect,
				)
				attempts += 1

		return AgentResponse(sql=sql, result=None, error=last_error, attempts=attempts, usage=self._llm.usage)