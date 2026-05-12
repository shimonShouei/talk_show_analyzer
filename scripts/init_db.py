"""Create all tables on the configured database.

Useful for local SQLite development and SLURM jobs where running alembic
migrations is overkill. For production (PostgreSQL), prefer `alembic upgrade head`.

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
