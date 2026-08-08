"""Append-only price history storage.

Supports CSV (default) and JSON, picked from the file extension. The file is
created on first write, including any missing parent directories.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .scraper import PriceRecord

FIELDNAMES = ("timestamp", "product", "url", "price", "currency")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class StorageError(Exception):
    """Raised when the history file exists but cannot be read."""


def _record_to_row(record: PriceRecord) -> dict[str, str]:
    return {
        "timestamp": record.timestamp.strftime(TIMESTAMP_FORMAT),
        "product": record.product,
        "url": record.url,
        "price": f"{record.price:.2f}",
        "currency": record.currency,
    }


def _row_to_record(row: dict) -> PriceRecord:
    return PriceRecord(
        timestamp=datetime.strptime(row["timestamp"], TIMESTAMP_FORMAT),
        product=row["product"],
        url=row.get("url", ""),
        price=float(row["price"]),
        currency=row.get("currency", "USD"),
    )


class PriceLog:
    """Reads and appends price observations for every tracked product."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.format = "json" if self.path.suffix.lower() == ".json" else "csv"

    # ------------------------------------------------------------------ write

    def append(self, record: PriceRecord) -> None:
        """Append a single observation."""
        self.append_many([record])

    def append_many(self, records: list[PriceRecord]) -> None:
        """Append several observations in one write."""
        if not records:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [_record_to_row(r) for r in records]

        if self.format == "json":
            existing = [_record_to_row(r) for r in self.read_all()]
            self.path.write_text(
                json.dumps(existing + rows, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return

        is_new = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerows(rows)

    # ------------------------------------------------------------------- read

    def read_all(self) -> list[PriceRecord]:
        """Every recorded observation, oldest first. Empty if no history yet."""
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return []

        try:
            if self.format == "json":
                raw_rows = json.loads(self.path.read_text(encoding="utf-8"))
            else:
                with self.path.open("r", newline="", encoding="utf-8") as handle:
                    raw_rows = list(csv.DictReader(handle))
        except (json.JSONDecodeError, csv.Error) as exc:
            raise StorageError(f"could not read {self.path}: {exc}") from exc

        records = []
        for row in raw_rows:
            try:
                records.append(_row_to_record(row))
            except (KeyError, ValueError, TypeError):
                continue  # skip corrupt lines rather than losing the whole log
        records.sort(key=lambda r: r.timestamp)
        return records

    def history(self, product: str | None = None, limit: int | None = None) -> list[PriceRecord]:
        """History for one product (or all), oldest first, optionally trimmed."""
        records = self.read_all()
        if product:
            wanted = product.strip().lower()
            records = [r for r in records if r.product.lower() == wanted]
        if limit is not None and limit > 0:
            records = records[-limit:]
        return records

    def latest(self, product: str) -> PriceRecord | None:
        """The most recent observation for a product, or None if never seen."""
        records = self.history(product)
        return records[-1] if records else None

    def product_names(self) -> list[str]:
        """Distinct product names present in the log."""
        seen: dict[str, None] = {}
        for record in self.read_all():
            seen.setdefault(record.product, None)
        return list(seen)


def summarize(records: list[PriceRecord]) -> dict[str, float] | None:
    """Min/max/average/current/change for a list of observations."""
    if not records:
        return None
    prices = [r.price for r in records]
    return {
        "count": len(prices),
        "current": prices[-1],
        "min": min(prices),
        "max": max(prices),
        "average": sum(prices) / len(prices),
        "change": prices[-1] - prices[0],
    }
