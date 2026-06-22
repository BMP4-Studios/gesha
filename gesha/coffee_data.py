"""Validated data-transfer model shared by scrapers and persistence services.

Parser and scraper code returns :class:`CoffeeData`; ``CoffeeService`` then
copies these normalized values into SQLAlchemy database models.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from pydantic import BaseModel, Field, field_validator

from gesha.normalization import normalize_tasting_notes


class CoffeeVariantData(BaseModel):
    """One purchasable Shopify variant belonging to a scraped coffee."""

    # Every field is optional except the display name because storefronts vary
    # in how much variant metadata they expose.
    shopify_variant_id: str | None = None
    name: str
    price_cents: int | None = None
    bag_size: str | None = None
    weight_grams: int | None = None
    availability: bool = True


class CoffeeData(BaseModel):
    """Portable representation of one scraped coffee before database storage."""

    # Roaster/name are the minimum identity needed to persist a scraped coffee.
    roaster: str
    name: str

    # Descriptive product facts may be missing depending on the source page.
    origin: str | None = None
    producer: str | None = None
    process: str | None = None
    varietal: str | None = None
    altitude: str | None = None
    tasting_notes: list[str] = Field(default_factory=list)
    roast_style: str | None = None

    # Product-level price/size is retained for display, while variants drive carts.
    price_cents: int | None = None
    bag_size: str | None = None

    # URL and availability decide cache identity and stale-product behavior.
    url: str | None = None
    availability: bool = True
    roast_date: date | None = None

    # Variants are normalized before persistence so the DB does not depend on
    # raw Shopify payload shapes.
    variants: list[CoffeeVariantData] = Field(default_factory=list)

    @field_validator("roaster", "name", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        """Trim identity fields so updates can match existing database rows."""
        # Leave non-string values alone so Pydantic can report invalid input.
        return value.strip() if isinstance(value, str) else value

    @field_validator("tasting_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Iterable[str] | str | None) -> list[str]:
        """Store tasting notes consistently for display and flavor filtering."""
        return normalize_tasting_notes(value)
