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
from time import perf_counter, time
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


MAX_TABLE_PREVIEW_ROWS = 1000
QUERY_CACHE_MAX_ENTRIES = 50
QUERY_CACHE_TTL_SECONDS = 15 * 60


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


def _prune_query_cache(cache: dict, now_ts: float) -> None:
	"""Remove expired entries and enforce max-cache size (LRU by insertion order)."""
	expired_keys = [
		key
		for key, entry in cache.items()
		if isinstance(entry, dict)
		and "ts" in entry
		and (now_ts - float(entry["ts"])) > QUERY_CACHE_TTL_SECONDS
	]
	for key in expired_keys:
		cache.pop(key, None)

	while len(cache) > QUERY_CACHE_MAX_ENTRIES:
		oldest_key = next(iter(cache))
		cache.pop(oldest_key, None)


def _get_cached_response(cache: dict, key: tuple[str, str], now_ts: float):
	"""Return cached response if valid and promote it as most recently used."""
	entry = cache.get(key)
	if entry is None:
		return None

	if isinstance(entry, dict):
		if "response" not in entry:
			cache.pop(key, None)
			return None
		if (now_ts - float(entry.get("ts", 0))) > QUERY_CACHE_TTL_SECONDS:
			cache.pop(key, None)
			return None
		response = entry["response"]
	else:
		response = entry

	cache.pop(key, None)
	cache[key] = {"response": response, "ts": now_ts}
	return response


def _set_cached_response(cache: dict, key: tuple[str, str], response, now_ts: float) -> None:
	"""Store a response and keep the cache within configured limits."""
	cache.pop(key, None)
	cache[key] = {"response": response, "ts": now_ts}
	_prune_query_cache(cache, now_ts)


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

	with st.form("query_form"):
		question = st.text_area(
			"Ask a question about your data",
			placeholder="e.g. Show the total orders by user for the last 7 days",
			height=120,
		)
		run_clicked = st.form_submit_button("Run query")

	if "query_cache" not in st.session_state:
		st.session_state.query_cache = {}

	if run_clicked:
		if not db_input.strip():
			st.error("Please provide a database path or SQLAlchemy URL.")
			st.stop()

		if not question.strip():
			st.error("Please enter a question.")
			st.stop()

		db_uri = normalize_db_uri(db_input)
		cache_key = (db_uri, question.strip().lower())
		now_ts = time()
		timings: dict[str, float] = {}
		cache_hit = False

		# Cache agent in session state — avoids rebuilding LLM + DB on every click
		if "agent" not in st.session_state or st.session_state.get("agent_db_uri") != db_uri:
			t0 = perf_counter()
			st.session_state.agent = create_agent(db_uri)
			st.session_state.agent_db_uri = db_uri
			timings["agent_init"] = perf_counter() - t0

		_prune_query_cache(st.session_state.query_cache, now_ts)
		response = _get_cached_response(st.session_state.query_cache, cache_key, now_ts)
		if response is not None:
			cache_hit = True
		else:
			with st.spinner("Running QueryAI agent..."):
				t0 = perf_counter()
				response = st.session_state.agent.answer_question(question)
				timings["agent_total"] = perf_counter() - t0
			_set_cached_response(st.session_state.query_cache, cache_key, response, now_ts)

		st.session_state.last_run = {
			"question": question,
			"db_uri": db_uri,
			"response": response,
			"timings": timings,
			"cache_hit": cache_hit,
		}

	if "last_run" not in st.session_state:
		st.info("Enter a question and click Run query.")
		st.stop()

	response = st.session_state.last_run["response"]
	timings = st.session_state.last_run.get("timings", {})
	cache_hit = st.session_state.last_run.get("cache_hit", False)

	with st.sidebar.expander("Performance", expanded=False):
		st.write(f"Result cache hit: {'yes' if cache_hit else 'no'}")
		st.write(f"Cache size: {len(st.session_state.query_cache)}/{QUERY_CACHE_MAX_ENTRIES}")
		st.write(f"Cache TTL: {QUERY_CACHE_TTL_SECONDS}s")
		for label, seconds in timings.items():
			st.write(f"{label}: {seconds:.3f}s")

	st.subheader("Generated SQL")
	st.code(response.sql or "<no SQL generated>", language="sql")

	# Keep the SQL editor in sync with the newest generated SQL
	seed_sql = response.sql or ""
	if st.session_state.get("editable_sql_seed") != seed_sql:
		st.session_state.editable_sql = seed_sql
		st.session_state.editable_sql_seed = seed_sql

	with st.form("edited_sql_form"):
		st.text_area(
			"Edit SQL and run manually",
			key="editable_sql",
			height=220,
			help="Only read-only SELECT-style queries are allowed.",
		)
		run_edited_clicked = st.form_submit_button("Run edited SQL")

	if run_edited_clicked:
		edited_sql = st.session_state.get("editable_sql", "").strip()
		if not edited_sql:
			st.error("Please enter SQL to run.")
			st.stop()

		with st.spinner("Running edited SQL..."):
			t0 = perf_counter()
			edited_response = st.session_state.agent.run_sql(
				edited_sql,
				question=st.session_state.last_run.get("question", ""),
			)
			edit_timing = perf_counter() - t0

		st.session_state.last_run = {
			"question": st.session_state.last_run.get("question", ""),
			"db_uri": st.session_state.last_run.get("db_uri", ""),
			"response": edited_response,
			"timings": {"edited_sql_total": edit_timing},
			"cache_hit": False,
		}
		st.rerun()

	# ── Usage metrics ──
	if response.usage:
		with st.sidebar:
			st.markdown("---")
			st.subheader("Usage Metrics")
			col1, col2, col3 = st.columns(3)
			col1.metric("API Calls", response.usage.api_calls)
			col2.metric("Input Tokens", f"{response.usage.input_tokens:,}")
			col3.metric("Output Tokens", f"{response.usage.output_tokens:,}")
			st.caption(f"Total tokens: {response.usage.total_tokens:,}")
			with st.expander("Call breakdown"):
				for d in response.usage.details:
					st.write(f"**{d['call']}** — in: {d['input_tokens']:,}  out: {d['output_tokens']:,}")

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
	if len(df) > MAX_TABLE_PREVIEW_ROWS:
		st.caption(
			f"Displaying first {MAX_TABLE_PREVIEW_ROWS:,} rows for UI responsiveness.",
		)
		df_display = df.head(MAX_TABLE_PREVIEW_ROWS)
	else:
		df_display = df

	chart_type, x_col, y_cols = _select_chart_options(df_display)
	if chart_type == "table" or x_col is None or not y_cols:
		st.dataframe(df_display)
		return

	st.dataframe(df_display)
	if chart_type == "bar":
		st.bar_chart(df_display.set_index(x_col)[y_cols])
	elif chart_type == "line":
		st.line_chart(df_display.set_index(x_col)[y_cols])


if __name__ == "__main__":  # pragma: no cover - Streamlit entry
	main()
