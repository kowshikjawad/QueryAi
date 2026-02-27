# QueryAI (CLI + Streamlit)

A minimal Text-to-SQL agent that connects to a SQL database, uses an LLM via LangChain to generate **read-only** SQL from natural language, executes it with SQLAlchemy, and presents the results via a CLI or Streamlit web UI.

## Quick start – CLI (SQLite)

1. Create or point to a SQLite database.
   - Easiest: use the bundled sample schema by running:

```powershell
python queryai/data/init_sample_db.py
```

    This will create `queryai/data/sample.db` with `users` and `orders` tables.

2. Set up a Python environment (3.10+), then install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure an LLM provider (OpenRouter or any OpenAI-compatible API). For example, for **OpenRouter**:

```powershell
$env:OPENROUTER_API_KEY = "your_openrouter_key_here"
$env:OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_MODEL_NAME = "meta-llama/llama-3.1-8b-instruct"  # or another model id
```

You can also use generic names (`API_KEY`, `API_BASE_URL`) or the legacy `OPENAI_API_KEY`/`OPENAI_BASE_URL` — the app will pick whichever is set.

4. Run the CLI (for the sample DB):

```powershell
python -m queryai.main --db-path queryai/data/sample.db --question "Show me the first 10 rows from the users table"
```

If `--question` is omitted, you will be prompted in the terminal.

## Quick start – Streamlit UI

1. Ensure dependencies are installed (including Streamlit and Plotly):

```powershell
pip install -r requirements.txt
```

2. Start the Streamlit app from the project root:

```powershell
streamlit run queryai/streamlit_app.py
```

3. In the web UI:
   - Enter a database path or full SQLAlchemy URL in the sidebar.
     - Examples: `queryai/data/sample.db`, `sqlite:///absolute/path/to.db`, `postgresql+psycopg2://user:pass@host:5432/dbname`.
   - Type a natural-language question.
   - Click **Run query** to see the generated SQL, results table, and optional bar/line charts for numeric columns.

## Design overview

- `queryai/src/db_manager.py` — `DatabaseManager` for SQLAlchemy connections, schema summary, and **read-only** query execution with a simple SQL heuristic.
- `queryai/src/llm_engine.py` — `LLMEngine` wrapper around a LangChain LLM, with prompts for initial SQL generation and error-based refinement. Prompts are mildly dialect-aware (SQLite/Postgres/MySQL, etc.).
- `queryai/src/text2sql_agent.py` — `TextToSQLAgent` implementing an agentic self-correction loop (up to 3 retries) and passing the detected DB dialect to the LLM.
- `queryai/src/app_core.py` — shared wiring for env loading, LLM construction, DB URI normalization, and `TextToSQLAgent` factory used by both CLI and Streamlit.
- `queryai/main.py` — CLI entrypoint that wires everything together.
- `queryai/streamlit_app.py` — Streamlit frontend for interactive questions, results, and basic visualizations.

Later sprints will add stronger safety/guardrails, logging, Docker, CI/CD, and advanced features like vector-store-based few-shot prompting and multi-model support.
