from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class Roaster(Base):
    __tablename__ = "roasters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    coffees: Mapped[List["Coffee"]] = relationship("Coffee", back_populates="roaster")

    def __repr__(self) -> str:
        return f"<Roaster name={self.name!r}>"


class TastingNote(Base):
    __tablename__ = "tasting_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    coffee_id: Mapped[int] = mapped_column(ForeignKey("coffees.id"), nullable=False)
    coffee: Mapped["Coffee"] = relationship(back_populates="tasting_notes")

    def __repr__(self) -> str:
        return f"<TastingNote name={self.name!r}>"


class Coffee(Base):
    __tablename__ = "coffees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roaster_id: Mapped[int] = mapped_column(ForeignKey("roasters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    origin: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    producer: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    process: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    varietal: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    altitude: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    roast_style: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bag_size: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    roast_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    roaster: Mapped[Roaster] = relationship(back_populates="coffees")
    tasting_notes: Mapped[List[TastingNote]] = relationship(back_populates="coffee", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Coffee name={self.name!r} roaster={self.roaster.name!r}>"
