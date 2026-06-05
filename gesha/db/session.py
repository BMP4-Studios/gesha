"""Database engine and session factory for Gesha's local SQLite cache.

CLI commands call ``init_db`` when creating or refreshing the catalog, then
create short-lived sessions consumed by ``CoffeeService``.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

SQLITE_URL = "sqlite:///gesha.db"

# Keep one engine and factory at module scope; commands create short sessions.
engine = create_engine(SQLITE_URL, echo=False, future=True)
SessionLocal: sessionmaker[Session] = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def init_db() -> None:
    """Create database tables before the first scrape or explicit ``init``."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a session used by CLI commands and persistence services."""
    return SessionLocal()
