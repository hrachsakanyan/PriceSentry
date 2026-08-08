"""PriceSentry command line interface.

    py -m src.main check              scrape every product, log it, alert
    py -m src.main history            show recorded price history
    py -m src.main chart              save a price-over-time PNG
    py -m src.main watch              keep checking on an interval
    py -m src.main products           list configured products
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .alerts import build_notifiers, dispatch, evaluate
from .chart import ChartError, plot_history
from .config import Config, ConfigError, DEFAULT_CONFIG_PATH, Product, load_config
from .logger import PriceLog, TIMESTAMP_FORMAT, summarize
from .scraper import PriceNotFound, PriceRecord, ScrapeError, scrape_product

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2


# ----------------------------------------------------------------- helpers


def _selected_products(config: Config, name: str | None) -> list[Product]:
    if not name:
        return config.products
    product = config.product_by_name(name)
    if product is None:
        known = ", ".join(p.name for p in config.products)
        raise ConfigError(f"unknown product {name!r}. Configured products: {known}")
    return [product]


def _status_line(record: PriceRecord, product: Product) -> str:
    line = f"  {record.product}: {record.format_price()}"
    if product.threshold is not None:
        marker = "<=" if record.price <= product.threshold else ">"
        line += f"  (threshold {product.threshold:,.2f}, price {marker} threshold)"
    return line


def _print_table(records: list[PriceRecord]) -> None:
    headers = ("TIMESTAMP", "PRODUCT", "PRICE")
    rows = [
        (
            r.timestamp.strftime(TIMESTAMP_FORMAT),
            r.product,
            f"{r.price:,.2f} {r.currency}",
        )
        for r in records
    ]

    widths = [
        max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(3)
    ]
    separator = "  ".join("-" * w for w in widths)

    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(separator)
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


# ---------------------------------------------------------------- commands


def cmd_check(config: Config, args: argparse.Namespace) -> int:
    """Scrape the selected products, append to the log and fire alerts."""
    products = _selected_products(config, args.product)
    log = PriceLog(config.storage_path)
    notifiers = build_notifiers(config.alerts)

    new_records: list[PriceRecord] = []
    failures = 0

    print(f"Checking {len(products)} product(s) at {datetime.now():%Y-%m-%d %H:%M:%S}")

    for product in products:
        previous = log.latest(product.name)
        try:
            record = scrape_product(product, config.request)
        except (ScrapeError, PriceNotFound) as exc:
            failures += 1
            print(f"  {product.name}: FAILED - {exc}", file=sys.stderr)
            continue

        new_records.append(record)
        print(_status_line(record, product))

        if previous is not None:
            delta = record.price - previous.price
            if delta:
                direction = "up" if delta > 0 else "down"
                print(f"      {direction} {abs(delta):,.2f} since {previous.timestamp:%Y-%m-%d %H:%M}")

        alerts = evaluate(record, product, previous, config.alerts.notify_on_drop)
        dispatch(alerts, notifiers)

    if new_records:
        log.append_many(new_records)
        print(f"\nLogged {len(new_records)} price(s) to {config.storage_path}")

    if failures and not new_records:
        return EXIT_ERROR
    return EXIT_OK


def cmd_history(config: Config, args: argparse.Namespace) -> int:
    """Print the recorded history, optionally filtered to one product."""
    log = PriceLog(config.storage_path)
    records = log.history(args.product, args.limit)

    if not records:
        target = f" for {args.product!r}" if args.product else ""
        print(f"No price history{target} yet. Run 'check' first.")
        return EXIT_OK

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "timestamp": r.timestamp.strftime(TIMESTAMP_FORMAT),
                        "product": r.product,
                        "url": r.url,
                        "price": r.price,
                        "currency": r.currency,
                    }
                    for r in records
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK

    _print_table(records)

    names = {r.product for r in records}
    for name in sorted(names):
        stats = summarize([r for r in records if r.product == name])
        if not stats:
            continue
        currency = next(r.currency for r in records if r.product == name)
        change = stats["change"]
        arrow = "-" if change == 0 else ("up" if change > 0 else "down")
        print(
            f"\n{name}: {int(stats['count'])} checks | "
            f"now {stats['current']:,.2f} {currency} | "
            f"min {stats['min']:,.2f} | max {stats['max']:,.2f} | "
            f"avg {stats['average']:,.2f} | {arrow} {abs(change):,.2f} overall"
        )
    return EXIT_OK


def cmd_chart(config: Config, args: argparse.Namespace) -> int:
    """Render the history as a PNG line chart."""
    log = PriceLog(config.storage_path)
    records = log.history(args.product)

    output = Path(args.output) if args.output else config.base_dir / "data" / "price_chart.png"
    title = f"Price history - {args.product}" if args.product else "Price history"

    try:
        path = plot_history(records, output, title)
    except ChartError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"Chart saved to {path}")
    return EXIT_OK


def cmd_watch(config: Config, args: argparse.Namespace) -> int:
    """Run `check` forever on a fixed interval."""
    interval = args.interval or config.interval_minutes
    print(
        f"Watching {len(_selected_products(config, args.product))} product(s) "
        f"every {interval} minute(s). Press Ctrl+C to stop."
    )

    while True:
        try:
            cmd_check(config, args)
        except Exception as exc:  # one bad round must not kill the watcher
            print(f"Check failed: {exc}", file=sys.stderr)

        next_run = datetime.now().timestamp() + interval * 60
        print(f"Next check at {datetime.fromtimestamp(next_run):%Y-%m-%d %H:%M:%S}\n")
        try:
            time.sleep(interval * 60)
        except KeyboardInterrupt:
            print("\nStopped.")
            return EXIT_OK


def cmd_products(config: Config, args: argparse.Namespace) -> int:
    """List what is configured, with the last recorded price for each."""
    log = PriceLog(config.storage_path)
    print(f"{len(config.products)} product(s) in {args.config}:\n")

    for product in config.products:
        latest = log.latest(product.name)
        print(f"  {product.name}")
        print(f"    url:       {product.url}")
        if product.selector:
            print(f"    selector:  {product.selector}")
        if product.threshold is not None:
            print(f"    threshold: {product.threshold:,.2f}")
        if latest:
            print(
                f"    last seen: {latest.format_price()} "
                f"at {latest.timestamp:%Y-%m-%d %H:%M}"
            )
        else:
            print("    last seen: never checked")
        print()
    return EXIT_OK


# --------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pricesentry",
        description="Track product prices over time and alert when they drop.",
    )
    parser.add_argument("--version", action="version", version=f"PriceSentry {__version__}")
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"path to the config file (default: {DEFAULT_CONFIG_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="scrape prices now, log them and alert")
    check.add_argument("-p", "--product", help="only check this product")
    check.set_defaults(func=cmd_check)

    history = subparsers.add_parser("history", help="show recorded price history")
    history.add_argument("-p", "--product", help="only show this product")
    history.add_argument("-n", "--limit", type=int, help="show only the last N entries")
    history.add_argument("--json", action="store_true", help="output JSON instead of a table")
    history.set_defaults(func=cmd_history)

    chart = subparsers.add_parser("chart", help="save a price-over-time chart (needs matplotlib)")
    chart.add_argument("-p", "--product", help="only chart this product")
    chart.add_argument("-o", "--output", help="output PNG path (default: data/price_chart.png)")
    chart.set_defaults(func=cmd_chart)

    watch = subparsers.add_parser("watch", help="check repeatedly on an interval")
    watch.add_argument("-p", "--product", help="only watch this product")
    watch.add_argument("-i", "--interval", type=int, help="minutes between checks")
    watch.set_defaults(func=cmd_watch)

    products = subparsers.add_parser("products", help="list configured products")
    products.set_defaults(func=cmd_products)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        return args.func(config, args)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except KeyboardInterrupt:
        print("\nStopped.")
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
