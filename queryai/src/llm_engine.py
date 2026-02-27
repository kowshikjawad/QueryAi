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

from dataclasses import dataclass
from typing import Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

BASE_TEXT_TO_SQL_SYSTEM_PROMPT = """You are an expert data analyst and SQL engineer.

You are connected to a READ-ONLY SQL database. You must:
- ONLY generate valid SQL for the target dialect (assume {dialect} by default).
- NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE.
- Prefer simple, single-statement queries.

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

Database schema:
{schema_summary}

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

		base_prompt = ChatPromptTemplate.from_template(BASE_TEXT_TO_SQL_SYSTEM_PROMPT)
		error_prompt = ChatPromptTemplate.from_template(ERROR_CORRECTION_PROMPT)
		answer_prompt = ChatPromptTemplate.from_template(ANSWER_GENERATION_PROMPT)

		parser = StrOutputParser()
		self._base_chain = base_prompt | self._llm | parser
		self._error_chain = error_prompt | self._llm | parser
		self._answer_chain = answer_prompt | self._llm | parser

	def generate_sql(
		self,
		question: str,
		schema_summary: str,
		dialect: str = "sqlite",
	) -> str:
		"""Generate an initial SQL query from natural language and schema."""

		sql = self._base_chain.invoke(
			{
				"question": question,
				"schema_summary": schema_summary,
				"dialect": dialect,
			}
		)
		return sql.strip()

	def refine_sql_on_error(
		self,
		question: str,
		schema_summary: str,
		previous_sql: str,
		error_message: str,
		dialect: str = "sqlite",
	) -> str:
		"""Ask the LLM to correct a previously generated SQL statement."""

		sql = self._error_chain.invoke(
			{
				"question": question,
				"schema_summary": schema_summary,
				"previous_sql": previous_sql,
				"error_message": error_message,
				"dialect": dialect,
			}
		)
		return sql.strip()

	def generate_answer(
		self,
		question: str,
		sql: str,
		results: str,
	) -> str:
		"""Generate a natural-language answer from query results."""

		answer = self._answer_chain.invoke(
			{
				"question": question,
				"sql": sql,
				"results": results,
			}
		)
		return answer.strip()

