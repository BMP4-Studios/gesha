from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field, field_validator


class CoffeeData(BaseModel):
    roaster: str
    name: str
    origin: Optional[str] = None
    producer: Optional[str] = None
    process: Optional[str] = None
    varietal: Optional[str] = None
    altitude: Optional[str] = None
    tasting_notes: List[str] = Field(default_factory=list)
    roast_style: Optional[str] = None
    price_cents: Optional[int] = None
    bag_size: Optional[str] = None
    url: Optional[str] = None
    availability: bool = True
    roast_date: Optional[date] = None

    @field_validator("roaster", "name", mode="before")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if isinstance(value, str) else value

    @field_validator("tasting_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Optional[Iterable[str]]) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip().lower()] if value.strip() else []
        return [note.strip().lower() for note in value if isinstance(note, str) and note.strip()]

    def get_price_display(self) -> str:
        return f"${self.price_cents / 100:.2f}" if self.price_cents is not None else "n/a"
