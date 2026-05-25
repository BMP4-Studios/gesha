"""SQLAlchemy schema for the locally cached coffee catalog.

The CLI opens this database through ``db.session`` and ``CoffeeService`` owns
creation, querying, and removal of these persisted records.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base used by table definitions and database initialization."""

    pass


def utc_now() -> datetime:
    """Supply UTC audit timestamps for inserted and updated coffee records."""
    return datetime.now(UTC)


class Roaster(Base):
    """A coffee company, shared by all cached products from that source."""

    __tablename__ = "roasters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    coffees: Mapped[list["Coffee"]] = relationship("Coffee", back_populates="roaster")

    def __repr__(self) -> str:
        """Return a compact representation useful during debugging."""
        return f"<Roaster name={self.name!r}>"


class TastingNote(Base):
    """One searchable tasting-note label associated with a cached coffee."""

    __tablename__ = "tasting_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    coffee_id: Mapped[int] = mapped_column(ForeignKey("coffees.id"), nullable=False)
    coffee: Mapped["Coffee"] = relationship(back_populates="tasting_notes")

    def __repr__(self) -> str:
        """Return a compact representation useful during debugging."""
        return f"<TastingNote name={self.name!r}>"


class Coffee(Base):
    """Persisted catalog entry created or refreshed from a scraped product."""

    __tablename__ = "coffees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roaster_id: Mapped[int] = mapped_column(ForeignKey("roasters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    producer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    process: Mapped[str | None] = mapped_column(String(64), nullable=True)
    varietal: Mapped[str | None] = mapped_column(String(128), nullable=True)
    altitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    roast_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bag_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    roaster: Mapped[Roaster] = relationship(back_populates="coffees")
    tasting_notes: Mapped[list[TastingNote]] = relationship(back_populates="coffee", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return a compact representation including its owning roaster."""
        return f"<Coffee name={self.name!r} roaster={self.roaster.name!r}>"
