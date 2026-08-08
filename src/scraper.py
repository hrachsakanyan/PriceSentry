"""Fetching a product page and pulling a price out of it.

Two independent halves so they can be tested separately:

* :func:`fetch_html`   - network (or local file) I/O
* :func:`extract_price` - pure HTML -> (price, currency) parsing
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .config import Product, RequestSettings

# Symbol -> ISO code. Enough coverage for the shops people actually track.
CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₽": "RUB",
    "֏": "AMD",
    "₩": "KRW",
    "₺": "TRY",
}

CURRENCY_CODES = (
    "USD", "EUR", "GBP", "JPY", "INR", "RUB", "AMD",
    "KRW", "TRY", "CAD", "AUD", "CHF", "SEK", "PLN",
)

# A run of digits that may contain thousands/decimal separators.
_NUMBER_RE = re.compile(r"\d[\d\s\u00a0.,]*\d|\d")

# Meta tags used by the common e-commerce templates, tried in order.
_PRICE_META_SELECTORS = (
    'meta[property="product:price:amount"]',
    'meta[itemprop="price"]',
    'meta[property="og:price:amount"]',
    'meta[name="twitter:data1"]',
)

_CURRENCY_META_SELECTORS = (
    'meta[property="product:price:currency"]',
    'meta[itemprop="priceCurrency"]',
    'meta[property="og:price:currency"]',
)


class ScrapeError(Exception):
    """The page could not be fetched."""


class PriceNotFound(Exception):
    """The page was fetched but no price could be located in it."""


@dataclass
class PriceRecord:
    """One observation of a product's price at a point in time."""

    timestamp: datetime
    product: str
    url: str
    price: float
    currency: str

    def format_price(self) -> str:
        return f"{self.price:,.2f} {self.currency}"


def parse_price(text: str) -> float:
    """Turn a human-readable price string into a float.

    Handles both separator conventions::

        "$1,299.00"   -> 1299.0
        "1.299,00 €"  -> 1299.0
        "USD 45.99"   -> 45.99
        "1 234,50"    -> 1234.5

    When only one separator is present the number of digits after it decides:
    exactly three means a thousands separator, otherwise it is the decimal
    point (``"1,234"`` -> 1234.0 but ``"1,23"`` -> 1.23).
    """
    if not text:
        raise PriceNotFound("empty price text")

    match = _NUMBER_RE.search(text)
    if not match:
        raise PriceNotFound(f"no number found in {text!r}")

    token = re.sub(r"[\s\u00a0]", "", match.group())
    has_comma = "," in token
    has_dot = "." in token

    if has_comma and has_dot:
        # Whichever separator comes last is the decimal one.
        decimal_sep = "," if token.rfind(",") > token.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        token = token.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        parts = token.split(sep)
        if len(parts) > 2 or len(parts[-1]) == 3:
            token = token.replace(sep, "")  # thousands separator
        else:
            token = token.replace(sep, ".")

    try:
        value = float(token)
    except ValueError:
        raise PriceNotFound(f"could not parse a price from {text!r}") from None

    if value <= 0:
        raise PriceNotFound(f"parsed a non-positive price from {text!r}")
    return value


def detect_currency(text: str) -> str | None:
    """Find a currency symbol or ISO code inside a price string."""
    if not text:
        return None
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    upper = text.upper()
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", upper):
            return code
    return None


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # lxml is optional
        return BeautifulSoup(html, "html.parser")


def _element_text(element) -> str:
    """Read a price from a tag - ``content`` for meta tags, text otherwise."""
    if element.name == "meta":
        return element.get("content", "")
    for attr in ("data-price", "data-price-amount", "content"):
        if element.has_attr(attr):
            return element[attr]
    return element.get_text(" ", strip=True)


def _iter_jsonld_offers(soup: BeautifulSoup):
    """Yield every ``offers`` object found in JSON-LD blocks on the page."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "price" in node or "lowPrice" in node:
                    yield node
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))


def extract_price(
    html: str,
    selector: str | None = None,
    default_currency: str | None = None,
) -> tuple[float, str]:
    """Extract ``(price, currency)`` from a product page.

    Tries the configured CSS selector first, then falls back to the structured
    metadata most shops embed: price meta tags and JSON-LD offers.
    """
    soup = _make_soup(html)
    currency: str | None = None

    if selector:
        element = soup.select_one(selector)
        if element is None:
            raise PriceNotFound(f"selector {selector!r} matched nothing on the page")
        text = _element_text(element)
        price = parse_price(text)
        currency = detect_currency(text)
    else:
        price, currency = _extract_without_selector(soup)

    if not currency:
        currency = _currency_from_meta(soup) or default_currency or "USD"
    return price, currency


def _extract_without_selector(soup: BeautifulSoup) -> tuple[float, str | None]:
    for meta_selector in _PRICE_META_SELECTORS:
        element = soup.select_one(meta_selector)
        if element is None:
            continue
        text = _element_text(element)
        try:
            return parse_price(text), detect_currency(text)
        except PriceNotFound:
            continue

    for offer in _iter_jsonld_offers(soup):
        raw = offer.get("price", offer.get("lowPrice"))
        try:
            return parse_price(str(raw)), offer.get("priceCurrency")
        except PriceNotFound:
            continue

    raise PriceNotFound(
        "no price found - pass a CSS selector for this product in config.json"
    )


def _currency_from_meta(soup: BeautifulSoup) -> str | None:
    for meta_selector in _CURRENCY_META_SELECTORS:
        element = soup.select_one(meta_selector)
        if element is not None:
            value = _element_text(element).strip().upper()
            if value:
                return value
    for offer in _iter_jsonld_offers(soup):
        if offer.get("priceCurrency"):
            return str(offer["priceCurrency"]).upper()
    return None


def _local_path(url: str) -> Path | None:
    """Return a filesystem path if ``url`` points at a local file, else None.

    Local files keep the demo config and the test-suite working offline.
    """
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        # file:///C:/x -> /C:/x on Windows
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return Path(path)
    if parsed.scheme in ("http", "https"):
        return None
    return Path(url)


def fetch_html(url: str, settings: RequestSettings | None = None) -> str:
    """Download a page (or read a local file) and return its HTML."""
    settings = settings or RequestSettings()

    local = _local_path(url)
    if local is not None:
        if not local.is_file():
            raise ScrapeError(f"local file not found: {local}")
        return local.read_text(encoding="utf-8", errors="replace")

    headers = {
        "User-Agent": settings.user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    last_error: Exception | None = None
    for attempt in range(settings.retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=settings.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < settings.retries:
                time.sleep(settings.retry_delay)

    raise ScrapeError(f"failed to fetch {url}: {last_error}") from last_error


def scrape_product(
    product: Product,
    settings: RequestSettings | None = None,
    now: datetime | None = None,
) -> PriceRecord:
    """Fetch a product page and return a timestamped :class:`PriceRecord`."""
    html = fetch_html(product.url, settings)
    price, currency = extract_price(html, product.selector, product.currency)
    return PriceRecord(
        timestamp=now or datetime.now(),
        product=product.name,
        url=product.url,
        price=price,
        currency=product.currency or currency,
    )
