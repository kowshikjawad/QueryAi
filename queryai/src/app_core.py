"""Shared application wiring for QueryAI (LLM + DB + Agent).

This module centralizes construction of the LLM, database manager, and
TextToSQLAgent so both the CLI and the Streamlit app can reuse the
same logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .db_manager import DatabaseManager, build_sqlite_uri_from_path
from .llm_engine import LLMEngine
from .text2sql_agent import TextToSQLAgent


@dataclass
class AppConfig:

	model_name: str
	temperature: float
	api_key: Optional[str]
	base_url: Optional[str]


def load_env() -> None:
	"""Load environment variables from common locations.

	This mirrors the behavior that previously lived in the CLI entry
	point so that other frontends (e.g. Streamlit) get the same config.
	"""

	load_dotenv()
	load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)


def build_app_config_from_env() -> AppConfig:
	"""Build AppConfig from environment variables for the LLM backend."""

	model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
	temperature = float(os.getenv("LLM_TEMPERATURE", "0"))

	api_key = (
		os.getenv("OPENROUTER_API_KEY")
		or os.getenv("API_KEY")
		or os.getenv("OPENAI_API_KEY")
	)
	base_url = (
		os.getenv("OPENROUTER_BASE_URL")
		or os.getenv("API_BASE_URL")
		or os.getenv("OPENAI_BASE_URL")
	)

	return AppConfig(
		model_name=model,
		temperature=temperature,
		api_key=api_key,
		base_url=base_url,
	)


def build_llm_from_config(config: AppConfig) -> ChatOpenAI:
	"""Construct a LangChain ChatOpenAI instance from AppConfig."""

	return ChatOpenAI(
		model=config.model_name,
		temperature=config.temperature,
		api_key=config.api_key,
		base_url=config.base_url,
	)


def normalize_db_uri(raw: str) -> str:
	"""Normalize a database identifier into a SQLAlchemy URI.

	Rules:
	- If the string already looks like a SQLAlchemy URL (contains
	  '://'), return it unchanged.
	- Otherwise treat it as a SQLite filesystem path and build an
	  appropriate URI using ``build_sqlite_uri_from_path``.
	"""

	raw = raw.strip()
	if "://" in raw:
		return raw
	return build_sqlite_uri_from_path(raw)


def create_agent(db_identifier: str, max_retries: int = 3) -> TextToSQLAgent:
	"""Create a TextToSQLAgent for the given DB identifier.

	The identifier can be either:
	- A raw filesystem path to a SQLite file.
	- A full SQLAlchemy URL (e.g. ``sqlite:///...``,
	  ``postgresql+psycopg2://...``).
	"""

	load_env()
	config = build_app_config_from_env()
	llm = build_llm_from_config(config)
	db_uri = normalize_db_uri(db_identifier)
	db = DatabaseManager(db_uri)
	engine = LLMEngine(llm)
	return TextToSQLAgent(db=db, llm_engine=engine, max_retries=max_retries)
