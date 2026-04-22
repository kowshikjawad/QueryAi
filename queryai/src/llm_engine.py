"""LLM engine abstraction for QueryAI.

This module wraps LangChain LLMs and provides helpers to generate and
refine SQL based on natural language questions and database schema
context. It is intentionally minimal for Sprint 1 and CLI-only usage.

The implementation is provider-agnostic: it expects any LangChain
``BaseLanguageModel``-compatible instance (e.g. ChatOpenAI, ChatOllama)
to be passed in from the application layer. This makes it easy to start
with a free or local model and later swap providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


@dataclass
class UsageStats:
	"""Tracks API call and token usage for a single user request."""

	api_calls: int = 0
	input_tokens: int = 0
	output_tokens: int = 0
	details: list = field(default_factory=list)  # per-call breakdown

	@property
	def total_tokens(self) -> int:
		return self.input_tokens + self.output_tokens

	def record(self, label: str, input_tok: int, output_tok: int) -> None:
		self.api_calls += 1
		self.input_tokens += input_tok
		self.output_tokens += output_tok
		self.details.append({
			"call": label,
			"input_tokens": input_tok,
			"output_tokens": output_tok,
		})

BASE_TEXT_TO_SQL_SYSTEM_PROMPT = """You are an expert data analyst and SQL engineer.

You are connected to a READ-ONLY SQL database. You must:
- ONLY generate valid SQL for the target dialect (assume {dialect} by default).
- NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE.
- Prefer simple, single-statement queries.
- Use identifiers exactly as they appear in the schema.
- Use identifiers exactly as they appear in the schema.
- For PostgreSQL, if a table/column contains uppercase letters (e.g. driverId), always use double quotes and preserve case.
- In dotted references with aliases, quote the column part too: a."driverId", a."routeId", d."id".
- Never emit unquoted camelCase identifiers in PostgreSQL.
- If users ask about "parcels behind" / "behind parcels" / "how many parcels ... behind", map that metric to "Assignment"."parcelsBehind" when present in schema.
- For driver-specific parcel-behind questions, join "Assignment" and "Driver" on "Assignment"."driverId" = "Driver"."id" and filter by "Driver"."name".

The database schema is:
{schema_summary}

User question:
{question}

Respond with ONLY the SQL query, no explanation, no markdown.
"""


ANSWER_GENERATION_PROMPT = """You are a helpful data analyst. The user asked:

"{question}"

The SQL query executed was:
{sql}

The query returned the following results (as a table):
{results}

Using the results above, provide a clear, concise, natural-language answer
to the user's original question. Do NOT include any SQL. If the result is
empty, say that no matching data was found.
"""


ERROR_CORRECTION_PROMPT = """You previously generated this SQL:

SQL:
{previous_sql}

When executed, the database returned this error:
{error_message}

Target SQL dialect: {dialect}

Database schema:
{schema_summary}

Important:
- Use identifiers exactly as they appear in the schema.
- For PostgreSQL, if a table/column contains uppercase letters, always double-quote and preserve case.

Please return a corrected SQL query that fixes the error while still
answering the original question:
{question}

Again, respond with ONLY the SQL query, no explanation, no markdown.
"""


@dataclass
class SQLGenerationResult:
	"""Container for SQL generation attempts."""

	sql: str
	attempts: int


class LLMEngine:
	"""Thin wrapper over a LangChain LLM for Text-to-SQL tasks."""

	def __init__(self, llm: BaseLanguageModel) -> None:
		self._llm = llm
		self.usage = UsageStats()

		base_prompt = ChatPromptTemplate.from_template(BASE_TEXT_TO_SQL_SYSTEM_PROMPT)
		error_prompt = ChatPromptTemplate.from_template(ERROR_CORRECTION_PROMPT)
		answer_prompt = ChatPromptTemplate.from_template(ANSWER_GENERATION_PROMPT)

		# Keep raw LLM chains (no StrOutputParser) so we can read token metadata
		self._base_chain = base_prompt | self._llm
		self._error_chain = error_prompt | self._llm
		self._answer_chain = answer_prompt | self._llm

	def reset_usage(self) -> None:
		"""Reset counters at the start of each user question."""
		self.usage = UsageStats()

	def _invoke_and_track(self, chain, payload: dict, label: str) -> str:
		"""Invoke a chain, extract token usage from the response metadata."""
		result = chain.invoke(payload)

		# LangChain AIMessage carries usage in response_metadata
		input_tok = 0
		output_tok = 0
		meta = getattr(result, "response_metadata", {}) or {}
		token_usage = meta.get("token_usage") or meta.get("usage") or {}
		if token_usage:
			input_tok = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0)
			output_tok = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0)

		self.usage.record(label, input_tok, output_tok)

		# Extract text content
		text = result.content if hasattr(result, "content") else str(result)
		return text.strip()

	def generate_sql(
		self,
		question: str,
		schema_summary: str,
		dialect: str = "sqlite",
	) -> str:
		"""Generate an initial SQL query from natural language and schema."""
		return self._invoke_and_track(
			self._base_chain,
			{"question": question, "schema_summary": schema_summary, "dialect": dialect},
			label="generate_sql",
		)

	def refine_sql_on_error(
		self,
		question: str,
		schema_summary: str,
		previous_sql: str,
		error_message: str,
		dialect: str = "sqlite",
	) -> str:
		"""Ask the LLM to correct a previously generated SQL statement."""
		return self._invoke_and_track(
			self._error_chain,
			{
				"question": question,
				"schema_summary": schema_summary,
				"previous_sql": previous_sql,
				"error_message": error_message,
				"dialect": dialect,
			},
			label="refine_sql",
		)

	def generate_answer(
		self,
		question: str,
		sql: str,
		results: str,
	) -> str:
		"""Generate a natural-language answer from query results."""
		return self._invoke_and_track(
			self._answer_chain,
			{"question": question, "sql": sql, "results": results},
			label="generate_answer",
		)

