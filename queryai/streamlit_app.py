"""Streamlit UI for QueryAI (Sprint 2).

This app provides a simple web interface on top of the existing
Text-to-SQL agent. It supports:

- Arbitrary SQLAlchemy DB URLs (SQLite, Postgres, MySQL, etc.).
- Natural-language questions.
- Display of generated SQL and tabular results.
- Optional basic visualizations (table / bar / line).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Ensure project root is on sys.path so `queryai` can be imported when
# this file is run directly via `streamlit run queryai/streamlit_app.py`.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from queryai.src.app_core import create_agent, normalize_db_uri

# Load .env so DATABASE_URI is available
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)

st.set_page_config(page_title="QueryAI", layout="wide")


def _get_default_db_uri() -> str:
	"""Return DATABASE_URI from env, or fall back to the local sample DB."""
	return os.getenv("DATABASE_URI", "queryai/data/sample.db")


def _select_chart_options(df: pd.DataFrame) -> tuple[str, Optional[str], Optional[list[str]]]:
	"""Return (chart_type, x_column, y_columns) from Streamlit widgets."""

	if df.empty:
		return "table", None, None

	chart_type = st.selectbox("Visualization", ["table", "bar", "line"], index=0)
	if chart_type == "table":
		return chart_type, None, None

	columns = list(df.columns)
	numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]

	if not numeric_cols:
		st.info("No numeric columns available for charts; falling back to table only.")
		return "table", None, None

	x_col = st.selectbox("X axis", columns, index=0)
	y_cols = st.multiselect("Y axis (numeric)", numeric_cols, default=numeric_cols[:1])
	if not y_cols:
		return "table", None, None

	return chart_type, x_col, y_cols


def main() -> None:
	st.sidebar.title("QueryAI – Text to SQL")
	st.sidebar.write("Connect to a SQL database and ask questions in plain English.")

	default_db = _get_default_db_uri()
	db_input = st.sidebar.text_input(
		"Database URI",
		value=default_db,
		type="password",
		help=(
			"Paste your Neon PostgreSQL URI, a local SQLite path, "
			"or any SQLAlchemy URL. Set DATABASE_URI in .env to auto-fill."
		),
	)

	question = st.text_area(
		"Ask a question about your data",
		placeholder="e.g. Show the total orders by user for the last 7 days",
		height=120,
	)

	col_run, col_status = st.columns([1, 3])
	with col_run:
		run_clicked = st.button("Run query")

	with col_status:
		st.write("")

	if not run_clicked:
		st.stop()

	if not db_input.strip():
		st.error("Please provide a database path or SQLAlchemy URL.")
		st.stop()

	if not question.strip():
		st.error("Please enter a question.")
		st.stop()

	db_uri = normalize_db_uri(db_input)

	with st.spinner("Running QueryAI agent..."):
		agent = create_agent(db_uri)
		response = agent.answer_question(question)

	st.subheader("Generated SQL")
	st.code(response.sql or "<no SQL generated>", language="sql")

	if response.error is not None or response.result is None:
		st.error(
			f"Query failed after {response.attempts} attempt(s):\n{response.error}",
		)
		st.stop()

	# Show natural-language answer
	if response.answer:
		st.subheader("Answer")
		st.write(response.answer)

	df = response.result.dataframe
	st.subheader(f"Result ({response.result.rowcount} row(s))")

	chart_type, x_col, y_cols = _select_chart_options(df)
	if chart_type == "table" or x_col is None or not y_cols:
		st.dataframe(df)
		return

	st.dataframe(df)
	if chart_type == "bar":
		st.bar_chart(df.set_index(x_col)[y_cols])
	elif chart_type == "line":
		st.line_chart(df.set_index(x_col)[y_cols])


if __name__ == "__main__":  # pragma: no cover - Streamlit entry
	main()
