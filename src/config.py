"""Configuration loading and validation.

The whole app is driven by a single JSON file (``config.json`` by default) so
that adding a product never requires touching the code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_CONFIG_PATH = "config.json"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ConfigError(Exception):
    """Raised when the config file is missing, malformed or incomplete."""


@dataclass
class Product:
    """A single tracked product."""

    name: str
    url: str
    selector: str | None = None
    threshold: float | None = None
    currency: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int) -> "Product":
        where = f"products[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where} must be an object")

        name = raw.get("name")
        url = raw.get("url")
        if not name or not isinstance(name, str):
            raise ConfigError(f"{where}.name is required and must be a string")
        if not url or not isinstance(url, str):
            raise ConfigError(f"{where}.url is required and must be a string")

        threshold = raw.get("threshold")
        if threshold is not None:
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                raise ConfigError(f"{where}.threshold must be a number") from None
            if threshold <= 0:
                raise ConfigError(f"{where}.threshold must be greater than 0")

        return cls(
            name=name,
            url=url,
            selector=raw.get("selector") or None,
            threshold=threshold,
            currency=raw.get("currency") or None,
        )


@dataclass
class RequestSettings:
    timeout: float = 15.0
    retries: int = 2
    retry_delay: float = 2.0
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RequestSettings":
        return cls(
            timeout=float(raw.get("timeout", 15.0)),
            retries=max(0, int(raw.get("retries", 2))),
            retry_delay=float(raw.get("retry_delay", 2.0)),
            user_agent=raw.get("user_agent") or DEFAULT_USER_AGENT,
        )


@dataclass
class EmailSettings:
    """SMTP settings. Credentials are read from the environment, never the file."""

    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = 587
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    password_env: str = "PRICESENTRY_SMTP_PASSWORD"

    @property
    def password(self) -> str | None:
        return os.environ.get(self.password_env)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EmailSettings":
        recipients = raw.get("recipients") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        return cls(
            enabled=bool(raw.get("enabled", False)),
            host=raw.get("host", "smtp.gmail.com"),
            port=int(raw.get("port", 587)),
            sender=raw.get("sender", ""),
            recipients=list(recipients),
            password_env=raw.get("password_env", "PRICESENTRY_SMTP_PASSWORD"),
        )


@dataclass
class AlertSettings:
    notify_on_drop: bool = True
    desktop: bool = False
    email: EmailSettings = field(default_factory=EmailSettings)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AlertSettings":
        return cls(
            notify_on_drop=bool(raw.get("notify_on_drop", True)),
            desktop=bool(raw.get("desktop", False)),
            email=EmailSettings.from_dict(raw.get("email") or {}),
        )


@dataclass
class Config:
    products: list[Product]
    storage_path: Path = Path("data/price_history.csv")
    request: RequestSettings = field(default_factory=RequestSettings)
    alerts: AlertSettings = field(default_factory=AlertSettings)
    interval_minutes: int = 360
    base_dir: Path = Path(".")

    def product_by_name(self, name: str) -> Product | None:
        """Case-insensitive lookup so the CLI is forgiving about `--product`."""
        wanted = name.strip().lower()
        for product in self.products:
            if product.name.lower() == wanted:
                return product
        return None


def _resolve_local_url(url: str, base_dir: Path) -> str:
    """Make a local sample-page path absolute, relative to the config file.

    Real ``http(s)`` and ``file://`` URLs are left untouched.
    """
    if urlparse(url).scheme in ("http", "https", "file"):
        return url
    candidate = base_dir / url
    return str(candidate.resolve()) if candidate.exists() else url


def load_config(path: str | os.PathLike[str] = DEFAULT_CONFIG_PATH) -> Config:
    """Read and validate a config file, resolving paths relative to it."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.json to config.json to get started."
        )

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a JSON object")

    raw_products = raw.get("products")
    if not isinstance(raw_products, list) or not raw_products:
        raise ConfigError("config must define a non-empty 'products' list")

    products = [Product.from_dict(item, i) for i, item in enumerate(raw_products)]

    base_dir = config_path.parent.resolve()
    for product in products:
        product.url = _resolve_local_url(product.url, base_dir)

    names = [p.name.lower() for p in products]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ConfigError(f"duplicate product names: {', '.join(sorted(duplicates))}")

    storage = raw.get("storage") or {}
    storage_path = Path(storage.get("path", "data/price_history.csv"))
    if not storage_path.is_absolute():
        storage_path = base_dir / storage_path

    schedule = raw.get("schedule") or {}
    interval = int(schedule.get("interval_minutes", 360))
    if interval < 1:
        raise ConfigError("schedule.interval_minutes must be at least 1")

    return Config(
        products=products,
        storage_path=storage_path,
        request=RequestSettings.from_dict(raw.get("request") or {}),
        alerts=AlertSettings.from_dict(raw.get("alerts") or {}),
        interval_minutes=interval,
        base_dir=base_dir,
    )
