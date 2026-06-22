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

    # SQLAlchemy reads subclasses of this base to build the metadata collection.
    pass


def utc_now() -> datetime:
    """Supply UTC audit timestamps for inserted and updated coffee records."""
    return datetime.now(UTC)


class Roaster(Base):
    """A coffee company, shared by all cached products from that source."""

    __tablename__ = "roasters"

    # Names are unique because each scraper maps to one display roaster.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # One roaster owns many coffees; deleting coffees is handled from Coffee.
    coffees: Mapped[list["Coffee"]] = relationship("Coffee", back_populates="roaster")

    def __repr__(self) -> str:
        """Return a compact representation useful during debugging."""
        return f"<Roaster name={self.name!r}>"


class TastingNote(Base):
    """One searchable tasting-note label associated with a cached coffee."""

    __tablename__ = "tasting_notes"

    # Notes are stored as rows instead of comma text so filtering by flavour is
    # a normal database join.
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

    # Identity and source ownership.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roaster_id: Mapped[int] = mapped_column(ForeignKey("roasters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Coffee metadata normalized from product pages and Shopify JSON.
    origin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    producer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    process: Mapped[str | None] = mapped_column(String(64), nullable=True)
    varietal: Mapped[str | None] = mapped_column(String(128), nullable=True)
    altitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    roast_style: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Product-level price/size is a fallback; cart optimization prefers variants.
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bag_size: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # URL and availability come from the latest successful scrape.
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Audit timestamps are useful when inspecting stale local caches.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships let service queries navigate from coffees to owners and notes.
    roaster: Mapped[Roaster] = relationship(back_populates="coffees")
    tasting_notes: Mapped[list[TastingNote]] = relationship(back_populates="coffee", cascade="all, delete-orphan")
    variants: Mapped[list["CoffeeVariant"]] = relationship(
        back_populates="coffee",
        cascade="all, delete-orphan",
        order_by="CoffeeVariant.weight_grams",
    )

    def __repr__(self) -> str:
        """Return a compact representation including its owning roaster."""
        return f"<Coffee name={self.name!r} roaster={self.roaster.name!r}>"


class CoffeeVariant(Base):
    """A purchasable size/price option exposed by a Shopify product."""

    __tablename__ = "coffee_variants"

    # Variants are owned by a single coffee and replaced on each scrape.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coffee_id: Mapped[int] = mapped_column(ForeignKey("coffees.id"), nullable=False)

    # Shopify's numeric variant ID is stored as text because external JSON is untyped.
    shopify_variant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Price and normalized weight are the inputs to unit-price and cart ranking.
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bag_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    coffee: Mapped[Coffee] = relationship(back_populates="variants")

    def __repr__(self) -> str:
        """Return a compact representation useful during cart debugging."""
        return f"<CoffeeVariant name={self.name!r} price_cents={self.price_cents!r}>"
