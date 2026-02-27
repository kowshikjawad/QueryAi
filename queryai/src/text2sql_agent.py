"""Core Text-to-SQL orchestration logic for QueryAI (Sprint 1).

This module coordinates between the DatabaseManager and LLMEngine to
implement a simple agentic reasoning loop with self-correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db_manager import DatabaseManager, QueryResult
from .llm_engine import LLMEngine


@dataclass
class AgentResponse:
	sql: str
	result: Optional[QueryResult]
	error: Optional[str]
	attempts: int
	answer: Optional[str] = None


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

	def answer_question(self, question: str) -> AgentResponse:
		schema_summary = self._db.get_schema_summary()
		dialect = getattr(self._db.engine.dialect, "name", "sqlite")

		attempts = 0
		last_error: Optional[str] = None
		sql: str = ""

		# Initial attempt
		sql = self._llm.generate_sql(
			question=question,
			schema_summary=schema_summary,
			dialect=dialect,
		)
		attempts += 1

		while attempts <= self._max_retries:
			try:
				result = self._db.run_read_only_query(sql)
				# Generate natural-language answer from the results
				results_text = result.dataframe.to_string(index=False)
				answer = self._llm.generate_answer(
					question=question,
					sql=sql,
					results=results_text,
				)
				return AgentResponse(sql=sql, result=result, error=None, attempts=attempts, answer=answer)
			except Exception as exc:  # noqa: BLE001 - top-level agent loop
				last_error = str(exc)
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

		return AgentResponse(sql=sql, result=None, error=last_error, attempts=attempts)