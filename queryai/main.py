"""CLI entry point for the QueryAI Text-to-SQL agent (Sprint 1).

This provides a minimal command-line interface that:
- Loads environment variables (e.g. LLM API keys).
- Connects to a SQLite database via SQLAlchemy.
- Uses an LLM (configured via LangChain) to translate natural language
  questions into SQL.
- Executes the SQL in a read-only manner with a simple self-correction
  loop handled by the TextToSQLAgent.
"""

from __future__ import annotations

import argparse
import sys

from .src.app_core import create_agent, load_env, normalize_db_uri


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QueryAI: Text-to-SQL over SQLite")
    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the SQLite database file (e.g. data/example.db)",
    )
    parser.add_argument(
        "--question",
        required=False,
        help="Natural language question to ask. If omitted, you will be prompted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    question = args.question or input("Enter your question about the data: ")

    # Normalize DB identifier into a SQLAlchemy URI and build agent
    load_env()
    db_uri = normalize_db_uri(args.db_path)
    agent = create_agent(db_uri)

    if not agent._db.test_connection():  # type: ignore[attr-defined]
        print("[ERROR] Could not connect to the SQLite database.")
        return 1

    response = agent.answer_question(question)

    print("\n--- Generated SQL ---")
    print(response.sql)

    if response.error is not None or response.result is None:
        print("\n[ERROR] Query failed after", response.attempts, "attempt(s):")
        print(response.error)
        return 1

    print("\n--- Result (", response.result.rowcount, "rows ) ---", sep="")
    # Render DataFrame as a simple text table
    print(response.result.dataframe.to_string(index=False))

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
