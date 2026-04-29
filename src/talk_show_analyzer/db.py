"""Database engine and session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.models import Base


def get_engine(database_url: str | None = None) -> Engine:
    """
    Create and return SQLAlchemy engine.

    Args:
        database_url: Database URL (uses settings.database_url if not provided)

    Returns:
        SQLAlchemy Engine
    """
    url = database_url or settings.database_url
    logger.info(f"Creating engine for: {url}")

    engine = create_engine(
        url,
        echo=False,  # Set to True for SQL debugging
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,  # Recycle connections after 1 hour
    )

    return engine


def init_db(database_url: str | None = None) -> None:
    """
    Initialize database (create all tables).

    Args:
        database_url: Database URL (uses settings.database_url if not provided)
    """
    engine = get_engine(database_url)
    logger.info("Creating all tables...")
    Base.metadata.create_all(engine)
    logger.info("Database initialized")


def get_session_factory(database_url: str | None = None) -> sessionmaker:
    """
    Create and return session factory.

    Args:
        database_url: Database URL (uses settings.database_url if not provided)

    Returns:
        sessionmaker instance
    """
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, class_=Session)


@contextmanager
def get_session(database_url: str | None = None) -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_session() as session:
            episode = session.query(Episode).first()

    Args:
        database_url: Database URL (uses settings.database_url if not provided)

    Yields:
        SQLAlchemy Session
    """
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
    except Exception as e:
        logger.error(f"Session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()
