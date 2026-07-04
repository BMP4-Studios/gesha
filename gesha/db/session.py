"""Database engine and session factory for Gesha's local SQLite cache.

CLI commands call ``init_db`` when creating or refreshing the catalog, then
create short-lived sessions consumed by ``CoffeeService``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DB_PATH = Path("gesha.db")
SQLITE_URL = f"sqlite:///{DB_PATH}"

# Keep one engine and factory at module scope; commands create short sessions.
engine = create_engine(SQLITE_URL, echo=False, future=True)

# ``expire_on_commit=False`` lets CLI rendering read objects after service methods commit without forcing implicit reloads.
SessionLocal: sessionmaker[Session] = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def init_db() -> None:
    """Create database tables before the first scrape or explicit ``init``."""
    # SQLAlchemy only creates missing tables; it does not drop user data.
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a session used by CLI commands and persistence services."""
    # The caller owns the session lifetime, usually via ``with get_session()``.
    return SessionLocal()
