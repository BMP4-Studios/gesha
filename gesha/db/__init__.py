"""Export database initialization used by setup and scraping workflows."""
from .session import init_db

__all__ = ["init_db"]
