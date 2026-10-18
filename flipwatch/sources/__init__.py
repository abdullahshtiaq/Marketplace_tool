from __future__ import annotations

from typing import Protocol

from ..models import Listing


class Source(Protocol):
    name: str

    def search(self, query: str, max_price: float | None = None) -> list[Listing]: ...

    def close(self) -> None: ...


class SourceError(RuntimeError):
    pass
