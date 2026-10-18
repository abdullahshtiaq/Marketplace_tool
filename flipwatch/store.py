from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .models import Listing

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    listing_key TEXT NOT NULL,
    watch TEXT NOT NULL,
    title TEXT,
    price REAL,
    url TEXT,
    year INTEGER,
    mileage_km INTEGER,
    comparable INTEGER NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    PRIMARY KEY (listing_key, watch)
);
CREATE TABLE IF NOT EXISTS alerted (
    listing_key TEXT NOT NULL,
    price REAL,
    alerted_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS primed (
    scope TEXT PRIMARY KEY,
    primed_at REAL NOT NULL
);
"""

_MISSING = object()


class Store:
    """Remembers which listings have been seen and alerted on."""

    def __init__(self, path: str | Path = "flipwatch.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def previous_price(self, listing: Listing, watch: str):
        """Price last recorded for this listing, or _MISSING if never seen."""
        row = self.conn.execute(
            "SELECT price FROM seen WHERE listing_key = ? AND watch = ?", (listing.key, watch)
        ).fetchone()
        return _MISSING if row is None else row[0]

    def record(self, listing: Listing, watch: str, comparable: bool = False) -> None:
        """Remember a listing. comparable=True lets its price count as a comp for auto valuation."""
        now = time.time()
        self.conn.execute(
            """INSERT INTO seen (listing_key, watch, title, price, url, year, mileage_km, comparable,
                                 first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (listing_key, watch)
               DO UPDATE SET price = excluded.price, title = excluded.title, year = excluded.year,
                             mileage_km = excluded.mileage_km, comparable = excluded.comparable,
                             last_seen = excluded.last_seen""",
            (listing.key, watch, listing.title, listing.price, listing.url, listing.year,
             listing.mileage_km, int(comparable), now, now),
        )
        self.conn.commit()

    def comp_prices(
        self,
        watch: str,
        *,
        exclude_key: str,
        min_price: float,
        days: float,
        year: int | None = None,
        year_window: int = 1,
    ) -> list[float]:
        """Recent asking prices of comparable listings for a watch (optionally near a model year)."""
        sql = """SELECT price FROM seen
                 WHERE watch = ? AND comparable = 1 AND listing_key != ?
                   AND price >= ? AND last_seen >= ?"""
        params: list = [watch, exclude_key, min_price, time.time() - days * 86400]
        if year is not None:
            sql += " AND year BETWEEN ? AND ?"
            params += [year - year_window, year + year_window]
        return [row[0] for row in self.conn.execute(sql, params)]

    def last_alert_price(self, listing: Listing):
        row = self.conn.execute(
            "SELECT price FROM alerted WHERE listing_key = ? ORDER BY alerted_at DESC LIMIT 1",
            (listing.key,),
        ).fetchone()
        return _MISSING if row is None else row[0]

    def mark_alerted(self, listing: Listing) -> None:
        self.conn.execute(
            "INSERT INTO alerted (listing_key, price, alerted_at) VALUES (?, ?, ?)",
            (listing.key, listing.price, time.time()),
        )
        self.conn.commit()

    def is_primed(self, scope: str) -> bool:
        return self.conn.execute("SELECT 1 FROM primed WHERE scope = ?", (scope,)).fetchone() is not None

    def mark_primed(self, scope: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO primed (scope, primed_at) VALUES (?, ?)", (scope, time.time())
        )
        self.conn.commit()


def is_missing(value) -> bool:
    return value is _MISSING
