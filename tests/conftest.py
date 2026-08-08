"""Shared fixtures. Everything here is offline - no test touches the network."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.scraper import PriceRecord

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def read_fixture():
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _read


@pytest.fixture
def make_record():
    """Build a PriceRecord with sensible defaults."""

    def _make(
        price: float,
        product: str = "Test Product",
        days_ago: int = 0,
        currency: str = "USD",
    ) -> PriceRecord:
        return PriceRecord(
            timestamp=datetime(2026, 1, 10, 12, 0, 0) - timedelta(days=days_ago),
            product=product,
            url="https://example.com/product",
            price=price,
            currency=currency,
        )

    return _make
