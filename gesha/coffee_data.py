"""Validated data-transfer model shared by scrapers and persistence services.

Parser and scraper code returns :class:`CoffeeData`; ``CoffeeService`` then
copies these normalized values into SQLAlchemy database models.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from pydantic import BaseModel, Field, field_validator
from gesha.normalization import normalize_tasting_notes


class CoffeeData(BaseModel):
    """Portable representation of one scraped coffee before database storage."""

    roaster: str
    name: str
    origin: str | None = None
    producer: str | None = None
    process: str | None = None
    varietal: str | None = None
    altitude: str | None = None
    tasting_notes: list[str] = Field(default_factory=list)
    roast_style: str | None = None
    price_cents: int | None = None
    bag_size: str | None = None
    url: str | None = None
    availability: bool = True
    roast_date: date | None = None

    @field_validator("roaster", "name", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        """Trim identity fields so updates can match existing database rows."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("tasting_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Iterable[str] | str | None) -> list[str]:
        """Store tasting notes consistently for display and flavor filtering."""
        return normalize_tasting_notes(value)
