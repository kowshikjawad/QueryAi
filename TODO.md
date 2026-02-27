# QueryAI TODO / Roadmap

Use this file to keep track of future improvements and experiments.
Check items off or add notes as you work.

## Sprint 1 polish (CLI core)

- [ ] Add nicer CLI output formatting (colors, better tables).
- [ ] Catch LLM rate-limit errors and show a friendly message.
- [ ] Add more unit tests (LLM prompts, TextToSQLAgent behavior).

## Sprint 2 – Streamlit UI + Dynamic Connections

- [ ] Build a Streamlit app with:
  - [ ] Sidebar for database URI input (SQLite/Postgres/MySQL).
  - [ ] Text box for natural-language question.
  - [ ] Panel showing generated SQL + results.
- [ ] Add basic visualizations (table / bar / line) using pandas + Plotly/Streamlit.
- [ ] Implement dynamic connection layer using SQLAlchemy URLs.

## Sprint 3 – Safety, Guardrails, Logging, MLOps

- [ ] Strengthen read-only enforcement (multi-layer checks, not just regex).
- [ ] Add simple SQL injection / dangerous-pattern detection.
- [ ] Log all (question, schema used, SQL, success/failure, latency).
- [ ] Add Dockerfile for running the app.
- [ ] Add GitHub Actions workflow (lint + tests on push/PR).

## Sprint 4 – Advanced Features

- [ ] Implement schema pruning:
  - [ ] Rank tables/columns by relevance to the question.
  - [ ] Only send top-N tables to the LLM.
- [ ] Add vector-store powered few-shot prompting (gold SQL examples).
- [ ] Add multi-model backend (OpenRouter, Ollama/local, direct OpenAI, etc.).
- [ ] Add configuration for per-environment settings (dev/stage/prod).

## Technical Debt / Ideas

- [ ] Cache `get_schema_summary()` result instead of recomputing per question.
- [ ] Add per-request timeout and retry/backoff for LLM calls.
- [ ] Add command-line flag to choose model/backend at runtime.
- [ ] Document common error messages and how to fix them (README section).
