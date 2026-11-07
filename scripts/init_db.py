"""Create all tables on the configured database.

Useful for local SQLite development and SLURM jobs where running alembic
migrations is overkill. For production (PostgreSQL), prefer `alembic upgrade head`.

Verified scope of this script (from reading it, not from running it against a
populated database during the November 2026 integration):

- It calls ``Base.metadata.create_all`` on whatever ``DATABASE_URL`` resolves to.
  ``talk_show_analyzer.db.init_db`` does the same call.
- ``create_all`` creates tables that are missing. It does not alter columns that
  already exist, does not stamp an Alembic revision, and does not insert rows.
- Historical local runs needed this once because the SQLite file started empty
  and ``get_session()`` does not create tables or commit on the way out.
- Alembic revisions in this tree are ``001`` (initial), ``002`` (``parts``),
  and ``003`` (part enrichment columns). An existing database should use
  ``alembic upgrade head`` so those revisions are applied and recorded.

Usage:
    python scripts/init_db.py
"""

from loguru import logger

from talk_show_analyzer.db import get_engine
from talk_show_analyzer.models import Base


def main() -> None:
    engine = get_engine()
    logger.info(f"Creating all tables on {engine.url}")
    Base.metadata.create_all(engine)
    logger.info("Done.")


if __name__ == "__main__":
    main()
