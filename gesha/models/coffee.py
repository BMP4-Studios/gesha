from __future__ import annotations

from datetime import date
from typing import Iterable

from pydantic import BaseModel, Field, field_validator
from gesha.normalization.normalize import NA_LABEL


class CoffeeData(BaseModel):
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
        return value.strip() if isinstance(value, str) else value

    @field_validator("tasting_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Iterable[str] | None) -> list[str]:
        if value is None:
            return []
        return [note.strip().lower() for note in value if isinstance(note, str) and note.strip()]

    def get_price_display(self) -> str:
        return f"${self.price_cents / 100:.2f}" if self.price_cents is not None else NA_LABEL
