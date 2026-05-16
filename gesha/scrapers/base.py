from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from gesha.models.coffee import CoffeeData


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self) -> List[CoffeeData]:
        """Scrape coffees from the source and return normalized data."""
        raise NotImplementedError
