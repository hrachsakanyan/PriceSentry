"""Tests for price parsing and HTML extraction."""

import pytest

from src.config import Product, RequestSettings
from src.scraper import (
    PriceNotFound,
    ScrapeError,
    detect_currency,
    extract_price,
    fetch_html,
    parse_price,
    scrape_product,
)


class TestParsePrice:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("$42.50", 42.50),
            ("42.50", 42.50),
            ("$1,299.00", 1299.00),
            ("1.299,00 €", 1299.00),
            ("USD 45.99", 45.99),
            ("1 234,50 AMD", 1234.50),
            ("Price: 89.5 GBP", 89.5),
            ("1,234", 1234.0),          # single comma + 3 digits -> thousands
            ("1,23", 1.23),             # single comma + 2 digits -> decimal
            ("1.234.567,89", 1234567.89),
            ("$1,234,567.89", 1234567.89),
            ("Now only 7", 7.0),
        ],
    )
    def test_parses_common_formats(self, text, expected):
        assert parse_price(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", ["", "Out of stock", "Free shipping!", "$0.00"])
    def test_rejects_unparseable_or_zero(self, text):
        with pytest.raises(PriceNotFound):
            parse_price(text)


class TestDetectCurrency:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("$42.50", "USD"),
            ("1.299,00 €", "EUR"),
            ("£89.50", "GBP"),
            ("15000 AMD", "AMD"),
            ("42.50", None),
        ],
    )
    def test_detects_symbols_and_codes(self, text, expected):
        assert detect_currency(text) == expected


class TestExtractPrice:
    def test_uses_css_selector(self, read_fixture):
        price, currency = extract_price(read_fixture("product_selector.html"), ".price-now")
        assert price == pytest.approx(42.50)
        assert currency == "USD"

    def test_selector_picks_the_right_element(self, read_fixture):
        """The old price is on the page too - the selector must not grab it."""
        price, _ = extract_price(read_fixture("product_selector.html"), ".price-was")
        assert price == pytest.approx(59.99)

    def test_missing_selector_raises(self, read_fixture):
        with pytest.raises(PriceNotFound, match="matched nothing"):
            extract_price(read_fixture("product_selector.html"), ".does-not-exist")

    def test_falls_back_to_meta_tags(self, read_fixture):
        price, currency = extract_price(read_fixture("product_meta.html"))
        assert price == pytest.approx(1299.00)
        assert currency == "EUR"

    def test_falls_back_to_jsonld(self, read_fixture):
        price, currency = extract_price(read_fixture("product_jsonld.html"))
        assert price == pytest.approx(89.50)
        assert currency == "GBP"

    def test_raises_when_no_price_anywhere(self, read_fixture):
        with pytest.raises(PriceNotFound):
            extract_price(read_fixture("product_no_price.html"))

    def test_default_currency_is_used_as_last_resort(self, read_fixture):
        _, currency = extract_price(
            read_fixture("product_selector.html").replace("$", ""),
            ".price-now",
            default_currency="AMD",
        )
        assert currency == "AMD"


class TestFetchHtml:
    def test_reads_a_local_file(self, fixtures_dir):
        html = fetch_html(str(fixtures_dir / "product_selector.html"))
        assert "price-now" in html

    def test_reads_a_file_url(self, fixtures_dir):
        html = fetch_html((fixtures_dir / "product_selector.html").as_uri())
        assert "price-now" in html

    def test_missing_local_file_raises(self, tmp_path):
        with pytest.raises(ScrapeError, match="local file not found"):
            fetch_html(str(tmp_path / "nope.html"))

    def test_network_failure_raises_scrape_error(self):
        settings = RequestSettings(timeout=1, retries=0)
        with pytest.raises(ScrapeError):
            fetch_html("http://localhost:9/definitely-not-listening", settings)


class TestScrapeProduct:
    def test_returns_a_timestamped_record(self, fixtures_dir):
        product = Product(
            name="Test Product",
            url=str(fixtures_dir / "product_selector.html"),
            selector=".price-now",
            threshold=50.0,
        )
        record = scrape_product(product)

        assert record.product == "Test Product"
        assert record.price == pytest.approx(42.50)
        assert record.currency == "USD"
        assert record.timestamp is not None
        assert record.format_price() == "42.50 USD"

    def test_configured_currency_overrides_the_page(self, fixtures_dir):
        product = Product(
            name="Test Product",
            url=str(fixtures_dir / "product_selector.html"),
            selector=".price-now",
            currency="AMD",
        )
        assert scrape_product(product).currency == "AMD"
