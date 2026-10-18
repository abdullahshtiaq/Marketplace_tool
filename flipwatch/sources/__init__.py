from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Listing


@dataclass
class SearchFilters:
    """Narrowing passed to the site's own search where it supports it.

    Results are still checked locally, so a site ignoring a filter is harmless.
    """

    max_price: float | None = None
    min_year: int | None = None
    max_year: int | None = None
    max_km: int | None = None


class Source(Protocol):
    name: str

    def search(self, query: str, filters: SearchFilters) -> list[Listing]: ...

    def close(self) -> None: ...


class SourceError(RuntimeError):
    pass
