from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base

SQLITE_URL = "sqlite:///gesha.db"

engine = create_engine(SQLITE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def init_db() -> None:
    """Create database tables if they do not already exist."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    return SessionLocal()
